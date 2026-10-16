/* Node built-ins only: decode both PNG paths and verify pixels across row batches. */
const assert=require('node:assert/strict'),zlib=require('node:zlib'),fs=require('node:fs'),path=require('node:path');
require('../assets/web/png-encoder.js');
function decode(bytes){
 const b=Buffer.from(bytes),data=[];assert.equal(b.subarray(0,8).toString('hex'),'89504e470d0a1a0a');
 let width,height,ended=false;
 for(let offset=8;offset<b.length;){
  const n=b.readUInt32BE(offset),type=b.toString('ascii',offset+4,offset+8),payload=b.subarray(offset+8,offset+8+n);
  // Independent bitwise CRC checks detect broken chunk framing and damaged data.
  let crc=0xffffffff;for(const byte of b.subarray(offset+4,offset+8+n)){crc^=byte;for(let k=0;k<8;k++)crc=crc&1?0xedb88320^(crc>>>1):crc>>>1;}
  assert.equal((crc^0xffffffff)>>>0,b.readUInt32BE(offset+8+n));
  if(type==='IHDR'){width=payload.readUInt32BE(0);height=payload.readUInt32BE(4);assert.equal(payload[9],6);}
  if(type==='IDAT')data.push(payload);if(type==='IEND')ended=true;offset+=n+12;
 }
 assert.ok(ended);const raw=zlib.inflateSync(Buffer.concat(data)),rgba=Buffer.alloc(width*height*4),stride=width*4;
 assert.equal(raw.length,(stride+1)*height);
 for(let y=0;y<height;y++){assert.equal(raw[y*(stride+1)],0);raw.copy(rgba,y*stride,y*(stride+1)+1,(y+1)*(stride+1));}
 return {width,height,rgba};
}
(async()=>{
 for(const compression of [true,false]){
  const width=123,height=400,source=Uint8Array.from({length:width*height*4},(_,i)=>(i*73+(i>>>9))%256);
  const encoder=FamilyPNG.create(width,height,{compression});
  await encoder.addRows(source.subarray(0,width*4*153),153);
  await encoder.addRows(source.subarray(width*4*153),height-153);
  const result=decode(await (await encoder.finish()).arrayBuffer());
  assert.equal(result.width,width);assert.equal(result.height,height);assert.deepEqual(result.rgba,Buffer.from(source));
 }
 const tall=FamilyPNG.create(1,40000);await tall.addRows(new Uint8Array(160000),40000);
 assert.equal(decode(await (await tall.finish()).arrayBuffer()).height,40000);
 const incomplete=FamilyPNG.create(2,3);await assert.rejects(incomplete.finish(),/incomplete/);await incomplete.abort();
 assert.throws(()=>FamilyPNG.create(0,1));
 console.log('PASS compressed/uncompressed pixels, CRC, row boundaries, 40000-pixel image and incomplete input');
})().catch(error=>{console.error(error);process.exitCode=1;});
