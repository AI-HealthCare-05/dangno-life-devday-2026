const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

for(const file of ['app.js','intro-retro-app.js']){
 const source=fs.readFileSync(path.join(__dirname,'../../src/frontend',file),'utf8');
 function harness(){
  const calls=[],state={lastKnownLocation:null},address={hidden:true};
  const nodes={'#emergency-address-form':address};
  const context=vm.createContext({state,Date:{now:()=>100000},navigator:{geolocation:{}},
   $:selector=>nodes[selector]||{},showEmergencyAddressForm:()=>{address.hidden=false},
   requestEmergencyFacilities:async position=>calls.push(['search',position.lat,position.lon]),
   currentBrowserPosition:async()=>({coords:{latitude:37.5,longitude:127}}),
   resetFacilitySearchUi:()=>{},setButtonBusy:()=>()=>{},
   setEmergencyFacilityStatus:(...args)=>calls.push(['status',args[0]]),
   geolocationFailureCopy:()=>['권한 거부'],geolocationFailureState:()=> 'permission'});
  for(const name of ['confirmEmergencyLocation','findNearbyEmergencyFacilities']){
   const match=source.match(new RegExp(`^async function ${name}\\([^]*?^}`,'m'));
   assert.ok(match,name);vm.runInContext(match[0],context);
  }
  return {context,state,calls,address};
 }
 test(file+': a denied location recheck clears a stale emergency reference and never searches it',async()=>{
  const h=harness();h.state.lastKnownLocation={lat:35,lon:129,confirmedAt:0};
  h.context.currentBrowserPosition=async()=>{throw {code:1}};
  await h.context.findNearbyEmergencyFacilities();
  assert.equal(h.state.lastKnownLocation,null);assert.equal(h.address.hidden,false);
  assert.equal(h.calls.filter(item=>item[0]==='search').length,0);
 });
 test(file+': recently confirmed location is used once, while a failed new confirmation removes it',async()=>{
  const h=harness();h.state.lastKnownLocation={lat:37,lon:127,confirmedAt:95000};
  await h.context.findNearbyEmergencyFacilities();
  assert.deepEqual(h.calls.find(item=>item[0]==='search'),['search',37,127]);
  h.context.currentBrowserPosition=async()=>{throw {code:1}};
  await h.context.confirmEmergencyLocation();
  assert.equal(h.state.lastKnownLocation,null);
 });
}
