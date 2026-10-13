// Small reusable CDP transport for local authored-fixture acceptance scripts.
// No browser service is launched or stopped here; only owned contexts are closed.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

async function connect(url) {
  const socket = new WebSocket(url);
  await new Promise(resolve => socket.addEventListener('open', resolve, {once:true}));
  let sequence = 0;
  const pending = new Map();
  const client = {socket, event:()=>{}, rpc:(method, params={})=>new Promise((resolve,reject)=>{
    const id=++sequence; pending.set(id,{resolve,reject}); socket.send(JSON.stringify({id,method,params}));
  })};
  socket.addEventListener('message', event=>{
    const message=JSON.parse(event.data);
    if (!message.id) {client.event(message);return;}
    const waiting=pending.get(message.id); pending.delete(message.id);
    message.error ? waiting.reject(Error(JSON.stringify(message.error))) : waiting.resolve(message.result);
  });
  return client;
}

export async function browserAcceptance({origin='http://127.0.0.1:5173',debug='http://127.0.0.1:9222'}={}) {
  const browser=await connect((await(await fetch(debug+'/json/version')).json()).webSocketDebuggerUrl);
  const contexts=[],clients=[],requests=[],exceptions=[];
  let page;
  async function evaluate(expression) {
    const result=await page.rpc('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function wait(expression) {
    for(let n=0;n<120;n++) {if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100));}
    throw Error('Rendered condition did not arrive: '+expression);
  }
  async function fresh(name) {
    const {browserContextId}=await browser.rpc('Target.createBrowserContext');contexts.push(browserContextId);
    const {targetId}=await browser.rpc('Target.createTarget',{url:'about:blank',browserContextId});
    const target=(await(await fetch(debug+'/json/list')).json()).find(item=>item.id===targetId);
    const client=await connect(target.webSocketDebuggerUrl);page=client;clients.push(client);
    Object.assign(client,{name,phase:'initial',loads:0,reads:[],inflight:new Set(),holdPath:'',held:null,failPath:'',losePost:'',lost:[]});
    const network=new Map();
    client.event=message=>{
      const value=message.params;
      if(message.method==='Page.loadEventFired')client.loads++;
      if(message.method==='Runtime.exceptionThrown')exceptions.push({context:name,details:value.exceptionDetails});
      if(message.method==='Network.requestWillBeSent') {
        const url=new URL(value.request.url);
        if(url.pathname.startsWith('/api/')) {
          client.inflight.add(value.requestId);
          const entry={context:name,phase:client.phase,path:url.pathname,query:url.search,method:value.request.method,body:value.request.postData};
          requests.push(entry);network.set(value.requestId,entry);
        }
      }
      if(['Network.loadingFinished','Network.loadingFailed'].includes(message.method))client.inflight.delete(value.requestId);
      if(message.method==='Network.responseReceived'&&network.has(value.requestId))network.get(value.requestId).status=value.response.status;
      if(message.method==='Network.loadingFinished'&&network.has(value.requestId)) {
        const entry=network.get(value.requestId);
        client.reads.push(client.rpc('Network.getResponseBody',{requestId:value.requestId}).then(result=>{
          const body=Buffer.from(result.body,result.base64Encoded?'base64':'utf8');entry.bodyBytes=body.length;
          try{entry.response=JSON.parse(body.toString());}catch{/* Preserve status for non-JSON failures. */}
        }).catch(()=>{}));
      }
      if(message.method==='Fetch.requestPaused') {
        const path=new URL(value.request.url).pathname;
        if(!value.responseStatusCode&&client.failPath===path) {
          client.failPath='';void client.rpc('Fetch.fulfillRequest',{requestId:value.requestId,responseCode:503,
            responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from('{"error":"Synthetic one-shot read failure"}').toString('base64')});
        }else if(value.responseStatusCode&&client.holdPath===path) {
          client.holdPath='';client.held=value.requestId;
        }else if(value.responseStatusCode&&value.request.method==='POST'&&client.losePost===path) {
          client.losePost='';client.lost.push({path,body:value.request.postData,committedStatus:value.responseStatusCode});
          void client.rpc('Fetch.failRequest',{requestId:value.requestId,errorReason:'Failed'});
        }else void client.rpc('Fetch.continueRequest',{requestId:value.requestId});
      }
    };
    await Promise.all([client.rpc('Page.enable'),client.rpc('Runtime.enable'),client.rpc('Network.enable')]);
    await client.rpc('Fetch.enable',{patterns:[{urlPattern:'*/api/*',requestStage:'Request'},{urlPattern:'*/api/*',requestStage:'Response'}]});
    await client.rpc('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
    await client.rpc('Page.navigate',{url:origin});await wait("!!document.querySelector('#saved-investigation')");
    return client;
  }
  const click=async selector=>{
    await wait(`document.querySelector(${JSON.stringify(selector)})&&!document.querySelector(${JSON.stringify(selector)}).disabled`);
    await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  };
  const clickText=async(text,root='document')=>{
    const expression=`[...${root}.querySelectorAll('button')].find(e=>e.textContent.trim()===${JSON.stringify(text)}&&!e.disabled)`;
    await wait(`!!(${expression})`);await evaluate(`(${expression}).click()`);
  };
  const fill=(selector,value)=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  const select=async(selector,value)=>{
    await wait(`[...document.querySelector(${JSON.stringify(selector)})?.options??[]].some(e=>e.value===${JSON.stringify(value)})`);
    await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  };
  const local=key=>evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(key)}))`);
  async function settle() {
    for(let n=0;n<100;n++) {
      if(!page.inflight.size){await new Promise(r=>setTimeout(r,150));if(!page.inflight.size){await Promise.all(page.reads);return;}}
      await new Promise(r=>setTimeout(r,50));
    }
    throw Error('API requests did not settle');
  }
  const screenshot=async path=>{
    await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
    await fs.writeFile(path,Buffer.from((await page.rpc('Page.captureScreenshot',{format:'png'})).data,'base64'));
  };
  async function reload() {
    const before=page.loads;await page.rpc('Page.reload',{ignoreCache:true});
    for(let n=0;n<120&&page.loads===before;n++)await new Promise(r=>setTimeout(r,100));
    assert(page.loads>before);await wait("!!document.querySelector('#saved-investigation')");
  }
  async function close() {
    for(const client of clients){await Promise.all(client.reads);await client.rpc('Fetch.disable').catch(()=>{});client.socket.close();}
    for(const browserContextId of contexts)await browser.rpc('Target.disposeBrowserContext',{browserContextId});
    browser.socket.close();
  }
  return {get page(){return page;},requests,exceptions,fresh,evaluate,wait,click,clickText,fill,select,local,settle,screenshot,reload,close};
}
