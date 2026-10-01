'use strict';
window.CodePresentation={
 readable(language,text,kind){const lang=String(language||'').toLowerCase();if(kind==='output')return true;if(['text','plaintext','plain','txt','console','output'].includes(lang))return true;if(lang&&!['unknown','none'].includes(lang))return false;return !/(?:^|\n)\s*(?:import\s+\w|from\s+[\w.]+\s+import|(?:async\s+)?(?:def|class|function)\s+\w|(?:const|let|var)\s+\w+\s*=|(?:if|for|while)\s+.+[:{]|(?:bash|python|powershell|npm|pip)\s+|[\w.]+\s*=\s*(?:[\[{]|["']|\d))|^\s*[\[{][\s\S]*[\]}]\s*$|<\/?(?:html|div|script|style)\b/m.test(text);}
};
