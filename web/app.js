const seed='3f9a7c2e1b8d4f6a0c5e9d2b7a4f1c8e6d3b0a5f';
const palettes=['#3549cf','#6951b5','#426c92'];
document.documentElement.style.setProperty('--blue',palettes[parseInt(seed.slice(0,8),16)%palettes.length]);
const $=id=>document.getElementById(id);let current=null,busy=false;
let submission=null;
try{submission=JSON.parse(sessionStorage.getItem('content-task')||'null');}catch{}
function taskRequest(fields){const fingerprint=JSON.stringify(fields);if(!submission||submission.fingerprint!==fingerprint)submission={fingerprint,id:'web-'+crypto.randomUUID()};try{sessionStorage.setItem('content-task',JSON.stringify(submission));}catch{}return {...fields,request_id:submission.id};}
const names={search_materials:'检索素材',update_plan:'调整计划',estimate_plan:'核算费用与时间',generate_script:'生成脚本',save_plan:'保存方案',finish_task:'结束任务',request_information:'请求补充'};
const states={completed:'已完成',incomplete:'未完成',waiting_input:'待补充',succeeded:'成功',failed:'失败',rejected:'未执行',pending:'待执行',skipped:'已复用'};
const initial=new Date(Date.now()+3600000);initial.setMinutes(initial.getMinutes()-initial.getTimezoneOffset());$('deadline').value=initial.toISOString().slice(0,16);
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function render(data,replay=false){current=data;$('mode-badge').textContent=replay?'真实记录回放':data.model_mode==='online'?'真实 API 运行':'离线流程演示';$('status').textContent=states[data.status]||data.status;
 $('plan-name').textContent=data.plan?.variant==='premium'?'完整内容方案':data.plan?.variant==='basic'?'精简内容方案':'尚未形成方案';
 $('plan-sub').textContent=data.plan_history?.length>1?`经过 ${data.plan_history.length} 版计划，找到下一步。`:'每个结果都由实际工具记录支持。';
 $('spent').textContent=data.cost?.spent??'—';$('limit').textContent=data.request?.budget??'—';$('budget-fill').style.width=`${Math.min(100,(data.cost?.spent||0)/Math.max(1,data.request?.budget||1)*100)}%`;
 $('minutes').textContent=(data.time?.simulated_minutes??'—')+' 分钟';$('calls').textContent=`${data.calls?.model??0} / ${data.calls?.tools??0}`;$('version').textContent=data.plan?'v'+data.plan.version:'—';
 $('notice').textContent=(replay?'这是已保存的历史案例，不是本次新运行。 ':'')+(data.reason||'请补充任务信息。');
 $('steps').replaceChildren();const labels=['检索','估算','生成','复查','保存'];(data.plan?.steps||labels.map(()=>({status:'pending'}))).forEach((s,i)=>{const el=node('div',undefined,'step '+(['succeeded','skipped'].includes(s.status)?'done':s.status==='failed'?'failed':''));el.append(node('b',s.status==='succeeded'?'✓':String(i+1)),node('span',labels[i]));el.title=states[s.status]||s.status;$('steps').append(el);});
 $('trace').replaceChildren();for(const t of data.trace||[]){if(t.kind!=='decision')continue;const d=node('details'),s=node('summary',names[t.action]||t.action);s.append(node('span',states[t.observation?.status]||''));d.append(s,node('p',t.reason||'模型已返回动作。'),node('pre',JSON.stringify({参数:t.parameters,结果:t.observation},null,2)));$('trace').append(d);}
 $('output-title').textContent=data.plan?.objective||data.request?.theme||'等待一份新方案';$('source').textContent=data.script?.source_ids?.join(' / ')||'无素材';$('script').replaceChildren();
 if(data.script){for(const s of data.script.sections){$('script').append(node('h4',s.title),node('p',s.text));}}else $('script').append(node('p',data.status==='waiting_input'?'系统需要更多信息，才能继续形成方案。':'本次没有生成可用脚本。你可以调整约束后重新运行。'));
 $('receipt').textContent=data.saved?`方案已保存至本地数据库。凭据：${data.saved.plan_id}`:'方案尚未保存。';$('download').disabled=false;
}
async function request(url,options){const r=await fetch(url,options);const d=await r.json();if(!r.ok)throw Error(d.error||'本机服务返回错误');return d;}
function lock(value){busy=value;document.body.classList.toggle('busy',value);document.querySelectorAll('form input,form textarea,form select,form button,[data-example]').forEach(e=>e.disabled=value);$('run').textContent=value?'模型正在规划，请稍候…':'开始规划 ↗';}
async function example(kind){if(busy)return;lock(true);try{render(await request('/api/example/'+kind),true);document.querySelectorAll('[data-example]').forEach(b=>b.classList.toggle('selected',b.dataset.example===kind));}catch(e){$('notice').textContent=e.message;}finally{lock(false);}}
document.querySelectorAll('[data-example]').forEach(b=>b.addEventListener('click',()=>example(b.dataset.example)));
$('brief').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;const deadline=new Date($('deadline').value);if(!Number.isFinite(deadline.getTime()))return;const body=taskRequest({theme:$('theme').value.trim(),budget:Number($('budget').value),deadline:deadline.toISOString(),mode:$('mode').value});lock(true);$('notice').textContent='本机正在执行任务。完成后会显示实际步骤；现在没有模拟进度。';try{render(await request('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}));document.querySelectorAll('[data-example]').forEach(b=>b.classList.remove('selected'));}catch(err){$('notice').textContent=err.message+'。你可以检查本机服务后重试。';}finally{lock(false);}});
$('new-task').addEventListener('click',()=>{submission=null;try{sessionStorage.removeItem('content-task');}catch{}$('notice').textContent='你已新建任务。下次提交会重新执行，并可能消耗 API 额度。';});
$('download').addEventListener('click',()=>{if(!current)return;const url=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download=current.request_id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
example('replan');

