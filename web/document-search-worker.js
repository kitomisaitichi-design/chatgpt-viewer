'use strict';
importScripts('document-search.js');
onmessage=e=>{try{postMessage(DocumentSearch.match(e.data.segments,e.data.query,e.data.options));}catch(error){postMessage({error:error.message});}};
