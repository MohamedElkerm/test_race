// Only sprites audited from the Live Results SFS_Tga.zip source are loaded here.
export const LED_IDENTITY_PATCH='RESULTS-20261020-2';
let identityPromise;
export function loadIdentity(){
 if(!identityPromise)identityPromise=(async()=>{
  const response=await fetch('/assets/results_identity/manifest.json',{cache:'no-store'});
  if(!response.ok)throw Error('Results identity manifest unavailable');
  const manifest=await response.json();
  if(manifest.id!=='FINS2026-FISU-SFS-RESULTS-20261014'||manifest.source_folder_id!=='1FR509dU4k0nw5l3eFZ99B9-6HTEJS3xY')throw Error('Unrecognised results identity source');
  const images={};
  for(const [key,asset] of Object.entries(manifest.assets)){
   if(!/^\/assets\/sfs\/[a-z0-9_]+\.png$/.test(asset.processed))throw Error('Results asset path rejected');
   const r=await fetch(asset.processed,{cache:'no-store'});
   if(!r.ok)throw Error('Results asset unavailable: '+key);
   const blob=await r.blob();
   if(globalThis.crypto?.subtle){
    const digest=await globalThis.crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
    const hash=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
    if(hash!==asset.png_sha256)throw Error('Results asset checksum mismatch: '+key);
   }
   const image=await createImageBitmap(blob);
   if(image.width!==asset.width||image.height!==asset.height)throw Error('Results asset dimensions differ: '+key);
   images[key]=image;
  }
  return{manifest,images};
 })().catch(error=>{identityPromise=undefined;throw error});
 return identityPromise;
}
export function containArtwork(context,image,box){
 // Never enlarge, crop, recolour, or distort an original sprite.
 const scale=Math.min(1,box.width/image.width,box.height/image.height);
 const width=image.width*scale,height=image.height*scale;
 const x=Math.floor(box.x+(box.width-width)/2),y=Math.floor(box.y+(box.height-height)/2);
 context.drawImage(image,x,y,width,height);
 return{x,y,width,height,source_width:image.width,source_height:image.height,fit:'contain',cropped:false,stretched:false};
}
