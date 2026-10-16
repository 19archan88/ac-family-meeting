/* Original local PNG encoder. Bounded raster memory; one image, no network or dependencies. */
(() => {
  'use strict';
  const table = Uint32Array.from({length:256},(_,n)=>{
    for(let k=0;k<8;k++) n=n&1?0xedb88320^(n>>>1):n>>>1;
    return n>>>0;
  });
  function chunk(type,data=new Uint8Array()) {
    const out=new Uint8Array(data.length+12), view=new DataView(out.buffer);
    view.setUint32(0,data.length);
    for(let i=0;i<4;i++)out[i+4]=type.charCodeAt(i);
    out.set(data,8);
    let crc=0xffffffff;
    for(let i=4;i<out.length-4;i++)crc=table[(crc^out[i])&255]^(crc>>>8);
    view.setUint32(out.length-4,(crc^0xffffffff)>>>0);
    return out;
  }
  function create(width,height,{compression=true}={}) {
    if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width>0x7fffffff||height>0x7fffffff)throw new Error('Invalid PNG dimensions');
    const header=new Uint8Array(13), info=new DataView(header.buffer);
    info.setUint32(0,width);info.setUint32(4,height);header[8]=8;header[9]=6;
    const parts=[new Uint8Array([137,80,78,71,13,10,26,10]),chunk('IHDR',header)];
    let written=0,closed=false,writer,pump,adlerA=1,adlerB=0;
    if(compression && typeof CompressionStream!=='undefined'){
      const stream=new CompressionStream('deflate');writer=stream.writable.getWriter();
      const reader=stream.readable.getReader();
      pump=(async()=>{while(true){const {done,value}=await reader.read();if(done)break;parts.push(chunk('IDAT',value));}})();
      pump.catch(()=>{}); // finish propagates errors; never leave an unhandled rejection.
    }else parts.push(chunk('IDAT',new Uint8Array([0x78,0x01])));
    async function addRows(rgba,rows) {
      if(closed||!Number.isInteger(rows)||rows<1||written+rows>height||rgba.length!==width*4*rows)throw new Error('Invalid PNG row data');
      const stride=width*4, scanlines=new Uint8Array((stride+1)*rows);
      for(let y=0;y<rows;y++)scanlines.set(rgba.subarray(y*stride,(y+1)*stride),y*(stride+1)+1);
      if(writer)await writer.write(scanlines);
      else {
        // Portable zlib stored blocks for browsers without CompressionStream.
        for(let i=0;i<scanlines.length;i+=65535){
          const bytes=scanlines.subarray(i,Math.min(i+65535,scanlines.length));
          const block=new Uint8Array(bytes.length+5),v=new DataView(block.buffer);
          v.setUint16(1,bytes.length,true);v.setUint16(3,(~bytes.length)&65535,true);block.set(bytes,5);
          for(const b of bytes){adlerA=(adlerA+b)%65521;adlerB=(adlerB+adlerA)%65521;}
          parts.push(chunk('IDAT',block));
        }
      }
      written+=rows;
    }
    async function finish() {
      if(closed||written!==height)throw new Error('PNG is incomplete');
      closed=true;
      if(writer){await writer.close();await pump;}
      else {
        const end=new Uint8Array([1,0,0,255,255,0,0,0,0]);
        new DataView(end.buffer).setUint32(5,((adlerB<<16)|adlerA)>>>0);parts.push(chunk('IDAT',end));
      }
      parts.push(chunk('IEND'));
      const result=new Blob(parts,{type:'image/png'});parts.length=0;return result;
    }
    async function abort(){closed=true;parts.length=0;if(writer){try{await writer.abort();await pump;}catch(_){}}}
    return {addRows,finish,abort};
  }
  globalThis.FamilyPNG={create};
})();
