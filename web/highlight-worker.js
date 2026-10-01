'use strict';
try {importScripts('vendor/highlight.js?v=1.0.13');postMessage({ready:true});}
catch(error){postMessage({error:error.message});}
onmessage=event=>{
 const {id,text,language}=event.data;
 try {
  let lang=({python3:'python',py:'python',sh:'bash',shell:'bash',js:'javascript',ts:'typescript',text:'plaintext'})[language]||language;
  const render=(value,l)=>hljs.highlight(value,{language:l,ignoreIllegals:true}).value;
  let html=null;
  if(text.length<=65536&&self.hljs&&!['text','plaintext','plain','txt'].includes(language)){
   // Shell wrappers preserve the original command and colour the Python body.
   const heredoc=text.match(/^(.*?python(?:3)?\s+-\s*<<\s*['"]?(\w+)['"]?[^\n]*\n)([\s\S]*?)(\n\2['"]?\s*)$/);
   if(heredoc)html=render(heredoc[1],'bash')+render(heredoc[3],'python')+render(heredoc[4],'bash');
   else if(hljs.getLanguage(lang)&&!['unknown','plaintext'].includes(lang))html=render(text,lang);
   else {const detected=hljs.highlightAuto(text,['python','javascript','typescript','json','bash','xml','css','sql','cpp','csharp','powershell']);if(detected.relevance>=2)html=detected.value;}
  }
  postMessage({id,html});
 }catch(error){postMessage({id,error:error.message});}
};
