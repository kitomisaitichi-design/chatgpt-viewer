const assert=require('assert'),vm=require('vm'),fs=require('fs'),path=require('path');
const c={window:{addEventListener(){}},location:{href:'http://127.0.0.1:1234/',origin:'http://127.0.0.1:1234'},URL,URLSearchParams};vm.createContext(c);for(const file of ['midi-player.js','rich-media.js','widgets.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',file),'utf8'),c);
const midi=Buffer.from('4d546864000000060000000100604d54726b0000001000903c6460803c000090406460804000','hex'); // two half-second notes
const buffer=midi.buffer.slice(midi.byteOffset,midi.byteOffset+midi.length);new DataView(buffer).setUint32(18,Buffer.from(buffer).length-22);
const parsed=c.MidiPlayer.parse(buffer);assert.equal(parsed.notes.length,2);assert.equal(parsed.notes[0].note,60);assert.equal(parsed.notes[0].end,.5);assert.equal(parsed.notes[1].start,.5);assert.equal(parsed.duration,1);
assert.throws(()=>c.MidiPlayer.parse(new ArrayBuffer(2)),/Truncated/);const bad=buffer.slice(0);new DataView(bad).setUint16(12,0x8001);assert.throws(()=>c.MidiPlayer.parse(bad),/PPQ/);
const raw='\ue200image_group\ue202{"query":["sample image"],"layout":"carousel"}\ue201';const extracted=c.window.SavedWidgets.extract(raw);assert.equal(extracted.widgets[0].image_group.query[0],'sample image');assert(!extracted.text.includes('image_group'));
assert.equal(c.window.SavedWidgets.extract('```\n'+raw+'\n```').widgets.length,0);
const markup='<caption>A caption</caption> <text size="xs"><Link url="https://example.com/image" title="Image source"/></text>';const clean=c.window.RichMedia.markup(markup);assert(clean.includes('A caption'));assert(clean.includes('[Image source](<https://example.com/image>)'));assert(!clean.includes('<caption>'));assert.equal(c.window.RichMedia.markup('`'+markup+'`'),'`'+markup+'`');
console.log('Rich media: MIDI note timing, invalid/truncated/SMPTE handling, image_group extraction, captions/links and literal code preservation passed.');
