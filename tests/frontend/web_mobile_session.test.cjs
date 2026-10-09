const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source=fs.readFileSync('src/frontend/auth-session.js','utf8');
function setup(fetch){
 const values=new Map();
 const root={sessionStorage:{setItem:(k,v)=>values.set(k,v),getItem:k=>values.get(k),removeItem:k=>values.delete(k)},fetch,atob:s=>Buffer.from(s,'base64').toString()};
 vm.runInNewContext(source,{window:root,Date,JSON,Number,Object,Error});return root.GandangAuthSession;
}
test('restored bearer is verified; rejected account clears stored token',async()=>{
 let calls=[]; const auth=setup(async(url,options)=>{calls.push([url,options]);return {status:200,ok:true,json:async()=>({data:{id:7}})}});
 auth.save('synthetic-valid');assert.equal((await auth.resolve()).profile.id,7);
 assert.equal(calls[0][0],'/api/v1/users/me');assert.equal(calls[0][1].headers.Authorization,'Bearer synthetic-valid');
 auth.clear();assert.equal(auth.read(),null);
 const bad=setup(async()=>({status:401,ok:false}));bad.save('synthetic-bad');
 await assert.rejects(bad.resolve(),{status:401});assert.equal(bad.read(),null);
});
test('refresh token is independently validated; missing cookie requires login',async()=>{
 const auth=setup(async url=>({ok:true,status:200,json:async()=>url.endsWith('/refresh')?{access_token:'synthetic-refreshed'}:{id:12}}));
 assert.equal((await auth.resolve()).profile.id,12);
 const noCookie=setup(async()=>({ok:false,status:401}));await assert.rejects(noCookie.resolve(),{status:401});
});
test('transient server failure does not silently switch or erase a valid account',async()=>{
 const auth=setup(async()=>({ok:false,status:503}));auth.save('synthetic-valid');
 await assert.rejects(auth.resolve(),{status:503});assert.equal(auth.read(),'synthetic-valid');
});
