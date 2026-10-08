'use strict';
globalThis.MidiPlayer=(()=>{
 function parse(buffer){
  if(buffer.byteLength>8*1024*1024)throw Error('MIDI preview is limited to 8 MiB.');const v=new DataView(buffer);let p=0,events=0,order=0;
  const need=n=>{if(p+n>v.byteLength)throw Error('Truncated MIDI file.');},u8=()=>{need(1);return v.getUint8(p++);},u16=()=>u8()*256+u8(),u32=()=>u16()*65536+u16(),tag=()=>String.fromCharCode(u8(),u8(),u8(),u8());
  const variable=()=>{let value=0;for(let i=0;i<4;i++){const b=u8();value=value*128+(b&127);if(!(b&128))return value;}throw Error('Invalid MIDI variable-length value.');};
  if(tag()!=='MThd')throw Error('Not a standard MIDI file.');const header=u32();if(header<6)throw Error('Invalid MIDI header.');const format=u16(),tracks=u16(),division=u16();if(format>1||division&0x8000||!division)throw Error('Preview supports MIDI format 0/1 with PPQ timing.');if(tracks>128)throw Error('MIDI has too many tracks.');need(header-6);p+=header-6;const timeline=[];
  for(let t=0;t<tracks;t++){
   if(tag()!=='MTrk')throw Error('Invalid MIDI track.');const length=u32();need(length);const end=p+length;let tick=0,running=0;
   while(p<end){if(++events>200000)throw Error('MIDI has too many events.');tick+=variable();let status=u8();if(status<128){if(!running)throw Error('Invalid MIDI running status.');p--;status=running;}else if(status<240)running=status;
    if(status===255){running=0;const type=u8(),size=variable();need(size);if(type===81&&size===3)timeline.push({tick,order:order++,tempo:v.getUint8(p)*65536+v.getUint8(p+1)*256+v.getUint8(p+2)});p+=size;}
    else if(status===240||status===247){running=0;const size=variable();need(size);p+=size;}
    else if(status<240){const type=status>>4,channel=status&15,a=u8(),b=type===12||type===13?0:u8();if(a>127||b>127)throw Error('Invalid MIDI event data.');if(type===8||type===9||type===12||type===11)timeline.push({tick,order:order++,type,channel,a,b});}
    else throw Error('Unsupported MIDI system event.');if(p>end)throw Error('MIDI event exceeds track boundary.');
   }
  }
  timeline.sort((a,b)=>a.tick-b.tick||a.order-b.order);let tick=0,time=0,tempo=500000;const held=new Map(),programs=new Array(16).fill(0),notes=[];
  const finish=(key,at)=>{const note=held.get(key);if(note){note.end=at;notes.push(note);held.delete(key);}};
  for(const event of timeline){time+=(event.tick-tick)*tempo/division/1000000;tick=event.tick;if(time>1800)throw Error('MIDI preview is limited to 30 minutes.');if(event.tempo){tempo=event.tempo;continue;}const key=event.channel+':'+event.a;
   if(event.type===12)programs[event.channel]=event.a;
   else if(event.type===8||event.type===9&&!event.b)finish(key,time);
   else if(event.type===9){finish(key,time);held.set(key,{start:time,end:time+.25,note:event.a,velocity:event.b/127,channel:event.channel,program:programs[event.channel]});}
   else if(event.type===11&&[120,123].includes(event.a))for(const key of held.keys())if(key.startsWith(event.channel+':'))finish(key,time);
  }
  for(const key of held.keys())finish(key,time+.25);notes.sort((a,b)=>a.start-b.start);return {notes,duration:Math.max(.1,time,...notes.slice(-128).map(n=>n.end))};
 }
 function mount(host,url,name){
  const make=(tag,text='')=>{const el=document.createElement(tag);el.textContent=text;return el;},card=make('section');card.className='midi-player modern-media';const title=make('strong',name),status=make('p','MIDI synthesizer · Ready to load'),row=make('div'),play=make('button','Play'),time=make('span','0:00'),seek=make('input'),volume=make('input');row.className='midi-actions';seek.type=volume.type='range';seek.min=0;seek.max=100;seek.step=.1;seek.value=0;seek.setAttribute('aria-label','MIDI position');volume.min=0;volume.max=1;volume.step=.01;volume.value=.4;volume.setAttribute('aria-label','MIDI volume');row.append(play,time);const canvas=make('canvas');canvas.className='modern-media-meter';canvas.width=720;canvas.height=80;canvas.setAttribute('aria-label','Live MIDI visualization');canvas.setAttribute('role','img');play.className='modern-media-button modern-media-play';play.setAttribute('aria-label','Play MIDI');ViewerIcons.set(play,'play');seek.className='modern-media-seek';volume.className='modern-media-volume';card.append(title,status,canvas,row,seek,make('small','Volume'),volume);host.append(card);
  let doc=null,ctx=null,gain=null,offset=0,started=0,cursor=0,playing=false,disposed=false,timer=null,loading=false,stopMeter=null;const controller=new AbortController(),voices=new Set();
  const format=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0'),position=()=>playing?offset+ctx.currentTime-started:offset;
  function silence(){for(const voice of voices){try{voice.stop();}catch{}voice.disconnect();}voices.clear();}
  function pause(){if(playing)offset=Math.min(doc.duration,position());playing=false;clearInterval(timer);silence();ViewerIcons.set(play,'play');play.setAttribute('aria-label','Play MIDI');card.classList.remove('playing');}
  function pump(){if(!playing)return;const now=position();time.textContent=format(now)+' / '+format(doc.duration);seek.value=now/doc.duration*100;while(cursor<doc.notes.length&&doc.notes[cursor].start<now+.18){const note=doc.notes[cursor++];if(note.end<=now||voices.size>=48)continue;const oscillator=ctx.createOscillator(),envelope=ctx.createGain(),at=ctx.currentTime+Math.max(0,note.start-now),end=ctx.currentTime+Math.max(.03,note.end-now);oscillator.type=note.channel===9?'triangle':['sine','triangle','sawtooth','square'][Math.floor(note.program/32)];oscillator.frequency.value=440*2**((note.note-69)/12);envelope.gain.setValueAtTime(0,at);envelope.gain.linearRampToValueAtTime(note.velocity*.13,at+.008);envelope.gain.setValueAtTime(note.velocity*.13,Math.max(at+.008,end-.02));envelope.gain.linearRampToValueAtTime(0,end+.03);oscillator.connect(envelope);envelope.connect(gain);voices.add(oscillator);oscillator.onended=()=>{voices.delete(oscillator);oscillator.disconnect();envelope.disconnect();};oscillator.start(at);oscillator.stop(end+.04);}if(now>=doc.duration){pause();offset=0;seek.value=0;status.textContent='Finished · Synthesized MIDI playback';}}
  async function start(){if(loading)return;if(playing){pause();return;}loading=true;play.disabled=true;try{if(!doc){status.textContent='Loading MIDI…';const r=await fetch(url,{signal:controller.signal});if(!r.ok)throw Error('MIDI file unavailable.');doc=parse(await r.arrayBuffer());if(!doc.notes.length)throw Error('This MIDI file has no playable notes.');}if(disposed)return;ctx=ctx||new AudioContext();await ctx.resume();if(disposed)return;if(!gain){gain=ctx.createGain();const analyser=ctx.createAnalyser();analyser.fftSize=256;gain.connect(analyser);analyser.connect(ctx.destination);stopMeter=MediaPlayer.meter(canvas,analyser,()=>playing);}gain.gain.value=+volume.value;cursor=0;while(cursor<doc.notes.length&&doc.notes[cursor].end<=offset)cursor++;started=ctx.currentTime;playing=true;ViewerIcons.set(play,'pause');play.setAttribute('aria-label','Pause MIDI');card.classList.add('playing');status.textContent='Synthesized MIDI · '+doc.notes.length+' notes';timer=setInterval(pump,50);pump();}catch(error){if(!disposed)status.textContent=error.message;}finally{loading=false;play.disabled=false;}}
  play.onclick=start;seek.oninput=()=>{if(!doc)return;const resume=playing;pause();offset=+seek.value/100*doc.duration;time.textContent=format(offset)+' / '+format(doc.duration);if(resume)start();};volume.oninput=()=>{if(gain)gain.gain.setTargetAtTime(+volume.value,ctx.currentTime,.02);};
  return ()=>{disposed=true;controller.abort();pause();stopMeter?.();ctx?.close();};
 }
 return {parse,mount};
})();
