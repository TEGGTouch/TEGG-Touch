"""Public OSS update contract, shared by client and release tooling (stdlib only)."""

from dataclasses import dataclass
from datetime import date
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import zipfile

OSS_BASE = "https://sea-of-time.oss-cn-shanghai.aliyuncs.com/teggtouch/"
LATEST_URL = OSS_BASE + "latest.json"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_PACKAGE_BYTES = 2 * 1024**3 - 1
_CORE = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
_STABLE_VERSION = re.compile(_CORE)
_LOCAL_VERSION = re.compile(_CORE + r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?")


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str
    size: int
    sha256: str
    notes: str = ""
    released: str = ""

    def validate(self):
        if not isinstance(self.version, str) or not _STABLE_VERSION.fullmatch(self.version):
            raise ValueError("更新清单必须指向正式版本")
        if self.url != OSS_BASE + f"TEGGTouch_v{self.version}.zip":
            raise ValueError("更新包地址不是受信任的官方版本直链")
        if type(self.size) is not int or not 0 < self.size <= MAX_PACKAGE_BYTES:
            raise ValueError("更新包大小无效")
        if not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", self.sha256):
            raise ValueError("更新包缺少有效的 SHA256")
        if not isinstance(self.notes, str) or len(self.notes) > 64000:
            raise ValueError("更新说明无效")
        if not isinstance(self.released, str):
            raise ValueError("发布日期无效")
        date.fromisoformat(self.released)
        return self


def parse_manifest(data) -> ReleaseInfo:
    if not isinstance(data, dict) or data.get("product") != "TEGGTouch":
        raise ValueError("不是蛋挞更新清单")
    if type(data.get("schema")) is not int or data["schema"] != 1 or data.get("channel") != "stable":
        raise ValueError("不支持的更新清单格式或发布渠道")
    host = data.get("host")
    if not isinstance(host, dict):
        raise ValueError("更新清单缺少客户端安装包")
    release = ReleaseInfo(data.get("version"), host.get("url"), host.get("size"),
                          host.get("sha256"), data.get("notes", ""), data.get("released"))
    release.validate()
    if host.get("name") != f"TEGGTouch_v{release.version}.zip":
        raise ValueError("更新包文件名和版本不一致")
    return release


def is_newer(remote: str, local: str) -> bool:
    if not isinstance(remote, str) or not isinstance(local, str):
        return False
    remote, local = remote.lstrip("vV"), local.lstrip("vV")
    r, l = _STABLE_VERSION.fullmatch(remote), _LOCAL_VERSION.fullmatch(local)
    if not r or not l:
        return False
    rc, lc = tuple(map(int, r.groups())), tuple(map(int, l.groups()))
    return rc > lc or (rc == lc and "-" in local.split("+", 1)[0])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "更新源不允许重定向", headers, fp)


def open_update_url(url: str, timeout: float = 15):
    """Only contact our public OSS prefix; do not follow redirects."""
    parts, base = urlsplit(url), urlsplit(OSS_BASE)
    if (parts.scheme != base.scheme or parts.netloc != base.netloc
            or not parts.path.startswith(base.path) or parts.query or parts.fragment):
        raise ValueError("不受信任的更新地址")
    request = urllib.request.Request(url, headers={
        "User-Agent": "TEGGTouch-updater", "Cache-Control": "no-cache",
        "Accept-Encoding": "identity",
    })
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)


def validate_archive(path):
    """Validate before quitting the app; reject Windows traversal, ADS and symlinks."""
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        roots, names, expanded = [], set(), 0
        for item in entries:
            name = item.filename.replace("\\", "/")
            parts = name.rstrip("/").split("/")
            if (name.startswith("/") or any(p in ("", ".", "..") or ":" in p
                    or p.endswith((".", " ")) for p in parts)
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("更新包包含不安全的文件路径")
            key = name.rstrip("/").casefold()
            if key in names:
                raise ValueError("更新包包含重复文件路径")
            names.add(key)
            expanded += item.file_size
            if expanded > 8 * 1024**3 or item.flag_bits & 1:
                raise ValueError("更新包过大或包含加密文件")
            if not item.is_dir() and parts[-1] == "TEGGTouch.exe" and len(parts) <= 2:
                roots.append(parts[:-1])
        if len(roots) != 1:
            raise ValueError("更新包必须包含唯一的 TEGGTouch.exe")
        root = roots[0]
        if root and any(item.filename.replace("\\", "/").split("/")[0] != root[0] for item in entries):
            raise ValueError("更新包目录结构不一致")
        if archive.testzip():
            raise ValueError("更新包文件损坏")
