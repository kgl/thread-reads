(function(){var toc=document.getElementById('toc'),tg=document.getElementById('tg'),ls=[].slice.call(toc.querySelectorAll('a')),items=[],lock=false,timer=null,cur=null;
function sc(el){var p=el.parentElement;while(p&&p!==document.body){var o=getComputedStyle(p).overflowY;if((o==='auto'||o==='scroll')&&p.scrollHeight>p.clientHeight)return p;p=p.parentElement}return null}
ls.forEach(function(a){var el=document.getElementById(a.getAttribute('href').slice(1));if(el)items.push({a:a,el:el})});
var box=items.length?sc(items[0].el):null;var tgt=box||window;
function barH(){return tg.offsetHeight||0}
function cTop(){return box?box.getBoundingClientRect().top:0}
function mark(a){if(a===cur)return;cur=a;ls.forEach(function(x){x.classList.toggle('on',x===a)});var t=a.offsetTop-toc.clientHeight/2;if(a.offsetTop<toc.scrollTop||a.offsetTop+a.offsetHeight>toc.scrollTop+toc.clientHeight)toc.scrollTop=t}
function spy(){if(lock||!items.length)return;var line=cTop()+barH()+80,best=items[0];
var se=box||document.scrollingElement,atEnd=se.scrollTop+(box?box.clientHeight:innerHeight)>=se.scrollHeight-2;
for(var i=0;i<items.length;i++){if(items[i].el.getBoundingClientRect().top<=line)best=items[i];else break}
if(atEnd){var last=items[items.length-1];if(last.el.getBoundingClientRect().top<(box?box.clientHeight:innerHeight))best=last}
mark(best.a)}
function settle(){clearTimeout(timer);timer=setTimeout(function(){lock=false},150)}
tgt.addEventListener('scroll',function(){if(lock)settle();else spy()},{passive:true});
tgt.addEventListener('scrollend',function(){if(lock){clearTimeout(timer);lock=false}});
items.forEach(function(it){it.a.addEventListener('click',function(e){e.preventDefault();document.body.classList.remove('open');mark(it.a);lock=true;settle();
var off=barH()+28,y;if(box){y=it.el.getBoundingClientRect().top-cTop()+box.scrollTop-off;box.scrollTo({top:y,behavior:'smooth'})}else{y=it.el.getBoundingClientRect().top+pageYOffset-off;window.scrollTo({top:y,behavior:'smooth'})}})});
tg.addEventListener('click',function(){document.body.classList.toggle('open')});
window.addEventListener('resize',spy);spy();})();