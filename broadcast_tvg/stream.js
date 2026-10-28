export function subscribe(onState,onLost=()=>{}){
 let socket,timer,stopped=false,lastSeen=0,attemptAt=0,lost=false;
 function markLost(){if(!lost){lost=true;onLost()}}
 function connect(){
  if(stopped)return;attemptAt=performance.now();lastSeen=0;
  const current=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws');socket=current;
  current.onmessage=e=>{if(current!==socket||stopped)return;try{const state=JSON.parse(e.data);lastSeen=performance.now();lost=false;onState(state)}catch{markLost();current.close()}};
  current.onclose=()=>{if(current!==socket||stopped)return;markLost();timer=setTimeout(connect,500)};
  current.onerror=()=>{markLost();current.close()};
 }
 const watch=setInterval(()=>{if(!stopped&&lastSeen&&performance.now()-lastSeen>8000){markLost();if(socket&&socket.readyState<2)socket.close()}},1000);connect();
 return()=>{stopped=true;clearInterval(watch);clearTimeout(timer);socket?.close()};
}
