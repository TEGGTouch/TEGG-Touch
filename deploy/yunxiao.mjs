import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const name = "蛋挞产品版本归档";
const base = 'https://openapi-rdc.aliyuncs.com/oapi/v1/flow/organizations/69bd03dc706afd34aa5fa6c3';
const tokenFile = process.env.YUNXIAO_TOKEN_FILE || fileURLToPath(new URL('../../../TEGG-Homepage/令牌/yunxiao-token.txt', import.meta.url));
const token = (process.env.YUNXIAO_TOKEN || await fs.readFile(tokenFile, 'utf8')).replace(/^\uFEFF/, '').trim();
if (!token || /[\r\n]/.test(token)) throw new Error('A single-line Yunxiao token is required');
async function api(method, route, body) {
  const response = await fetch(base + route, {method, headers: {'x-yunxiao-token':token,'content-type':'application/json'}, body:body===undefined?undefined:JSON.stringify(body), signal:AbortSignal.timeout(30000)});
  const data=await response.json();
  if(!response.ok) throw new Error(`${method} ${route}: HTTP ${response.status}`);
  return data;
}
const list=await api('GET','/pipelines?perPage=100');
const pipeline=list.find(p=>p.pipelineName===name);
const command=process.argv[2]||'status';
if(command==='apply') {
  const content=await fs.readFile(new URL('./pipeline.yaml',import.meta.url),'utf8');
  const result=await api(pipeline?'PUT':'POST',pipeline?`/pipelines/${pipeline.pipelineId}`:'/pipelines',{name,content});
  console.log(JSON.stringify({name,pipelineId:pipeline?.pipelineId,result}));
} else {
  if(!pipeline)throw new Error('Pipeline has not been created');
  const route=`/pipelines/${pipeline.pipelineId}`;
  if(command==='run')console.log(JSON.stringify({pipelineId:pipeline.pipelineId,result:await api('POST',route+'/runs',{})}));
  else if(command==='status'){
    const runId=process.argv[3]||(await api('GET',route+'/runs?perPage=1'))[0]?.pipelineRunId;
    if(!runId||!/^\d+$/.test(String(runId)))throw new Error('No valid pipeline run');
    const run=await api('GET',`${route}/runs/${runId}`);
    console.log(JSON.stringify({name,pipelineId:pipeline.pipelineId,runId,status:run.status,triggerMode:run.triggerMode,commit:run.globalParams?.find(p=>p.key==='CI_COMMIT_SHA')?.value,jobs:run.stages.flatMap(s=>s.stageInfo.jobs.map(({id,name,status})=>({id,name,status})))},null,2));
  } else throw new Error('Usage: node deploy/yunxiao.mjs apply|run|status [RUN_ID]');
}
