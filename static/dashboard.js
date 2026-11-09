const DEMO=false;
const $=s=>document.querySelector(s),rp=n=>"Rp"+Math.round(n).toLocaleString("id-ID");
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const PAL=["#3b6ef5","#12a594","#f5a623","#e5484d","#8e4ec6","#30a46c","#ec6cb9","#7d8aa3"];
const mon=t=>t.slice(0,7),fmt=(m,o)=>new Date(m+"-01T00:00:00").toLocaleDateString("id-ID",o);
const bname=m=>m==="all"?"Semua bulan":fmt(m,{month:"long",year:"numeric"}),bs=m=>fmt(m,{month:"short",year:"2-digit"});
const sum=(a,t)=>a.filter(x=>x.tipe===t).reduce((s,x)=>s+x.jumlah,0);
const short=v=>v>=1e6?+(v/1e6).toFixed(1)+"jt":v>=1e3?Math.round(v/1e3)+"rb":v;
const col=(t,a)=>(t==="masuk"?"#12a594":"#e5484d")+(a||"");
let D=[],M=[],ch={},S={bln:"all",tab:"keluar",kat:null,q:"",tp:"all",sk:"tgl",sd:-1};

function demo(){let s=11;const r=()=>(s=s*16807%2147483647)/2147483647,o=[],pad=n=>String(n).padStart(2,"0");
const W=[["Makanan",.45,12,55],["Transport",.65,8,40],["Belanja",.75,40,300],["Hiburan",.83,30,150],["Kesehatan",.88,30,200],["Pendidikan",.91,50,250],["Lainnya",1,10,80]];
for(let m=0;m<6;m++){const d=new Date(2026,5+m,1),ym=d.getFullYear()+"-"+pad(d.getMonth()+1),last=m==5?9:28;
const add=(day,tipe,jumlah,kategori)=>o.push({tgl:ym+"-"+pad(day)+" 12:00:00",tipe,jumlah,kategori});
add(1,"masuk",6e6,"Gaji");if(m==2)add(15,"masuk",1.5e6,"Bonus");if(m%2)add(12,"masuk",Math.round(500+r()*700)*1e3,"Usaha");
add(2,"keluar",450e3,"Tagihan");if(last>=5)add(5,"keluar",350e3,"Tagihan");
for(let day=1;day<=last;day++){const n=1+Math.floor(r()*3);for(let k=0;k<n;k++){const p=r(),w=W.find(x=>p<=x[1]);add(day,"keluar",Math.round(w[2]+r()*(w[3]-w[2]))*1e3,w[0])}}}
return o}

function mk(id,cfg){ch[id]&&ch[id].destroy();cfg.options=Object.assign({responsive:true,maintainAspectRatio:false},cfg.options);ch[id]=new Chart(document.getElementById(id),cfg)}
function setBln(m){S.bln=m;S.kat=null;S.tp="all";$("#tp").value="all";$("#bln").value=m;render()}
function pick(k){S.kat=S.kat===k?null:k;S.tp=S.kat?S.tab:"all";$("#tp").value=S.tp;render()}

function render(){
const cs=getComputedStyle(document.documentElement);Chart.defaults.color=cs.getPropertyValue("--mu").trim();Chart.defaults.borderColor=cs.getPropertyValue("--ln").trim();
const all=S.bln==="all",[Y,Mo]=all?[0,0]:S.bln.split("-").map(Number),rows=D.filter(x=>all||mon(x.tgl)===S.bln),i=sum(rows,"masuk"),o=sum(rows,"keluar");
$("#kin").textContent=rp(i);$("#kout").textContent=rp(o);$("#ksal").textContent=rp(i-o);$("#ksal").className="v "+(i-o<0?"out":"in");
const n=new Date(),nd=all?Math.max(M.length,1):(n.getFullYear()===Y&&n.getMonth()+1===Mo)?n.getDate():new Date(Y,Mo,0).getDate();
$("#kavgl").textContent=all?"Rata-rata keluar per bulan":"Rata-rata keluar per hari";$("#kavg").textContent=rp(o/nd);
const pm=all?null:M[M.indexOf(S.bln)+1],pv=pm?sum(D.filter(x=>mon(x.tgl)===pm),"keluar"):0;
$("#kd").textContent=pv?(o>=pv?"▲ ":"▼ ")+Math.abs(Math.round((o-pv)/pv*100))+"% dari "+bname(pm):" ";
// donut kategori
const mp={};rows.filter(x=>x.tipe===S.tab).forEach(x=>mp[x.kategori]=(mp[x.kategori]||0)+x.jumlah);
const cats=Object.entries(mp).sort((a,b)=>b[1]-a[1]),tot=cats.reduce((s,c)=>s+c[1],0);
mk("c1",{type:"doughnut",data:{labels:cats.map(c=>c[0]),datasets:[{data:cats.map(c=>c[1]),backgroundColor:cats.map((c,j)=>PAL[j%8]),offset:cats.map(c=>c[0]===S.kat?14:0),borderWidth:0}]},
options:{cutout:"62%",plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>" "+c.label+": "+rp(c.raw)+" ("+Math.round(c.raw/tot*100)+"%)"}}},onClick:(e,el)=>el.length&&pick(cats[el[0].index][0])}});
$("#leg").innerHTML=cats.length?cats.map((c,j)=>`<div class="li${c[0]===S.kat?" on":""}" data-k="${esc(c[0])}"><span><i class="dot" style="background:${PAL[j%8]}"></i>${esc(c[0])}</span><b>${rp(c[1])} · ${Math.round(c[1]/tot*100)}%</b><div class="bar"><i style="width:${c[1]/tot*100}%;background:${PAL[j%8]}"></i></div></div>`).join(""):'<div class="empty">Belum ada data</div>';
// tren harian / bulanan
let lb,gi,go;
if(all){const ms=[...M].reverse();lb=ms.map(bs);gi=ms.map(m=>sum(D.filter(x=>mon(x.tgl)===m),"masuk"));go=ms.map(m=>sum(D.filter(x=>mon(x.tgl)===m),"keluar"))}
else{const dim=new Date(Y,Mo,0).getDate();gi=Array(dim).fill(0);go=Array(dim).fill(0);rows.forEach(x=>{(x.tipe==="masuk"?gi:go)[+x.tgl.slice(8,10)-1]+=x.jumlah});lb=gi.map((_,d)=>d+1)}
$("#t2").textContent=all?"Pemasukan dan pengeluaran per bulan":"Per hari, "+bname(S.bln);
mk("c2",{type:"bar",data:{labels:lb,datasets:[{label:"Masuk",data:gi,backgroundColor:col("masuk")},{label:"Keluar",data:go,backgroundColor:col("keluar")}]},
options:{scales:{y:{ticks:{callback:short}}},plugins:{tooltip:{callbacks:{label:c=>" "+c.dataset.label+": "+rp(c.raw)}}}}});
// 6 bulan terakhir (klik = pilih bulan)
const m6=M.slice(0,6).reverse();$("#w3").style.display=all?"none":"";
if(!all)mk("c3",{type:"bar",data:{labels:m6.map(bs),datasets:["masuk","keluar"].map(t=>({label:t==="masuk"?"Masuk":"Keluar",data:m6.map(m=>sum(D.filter(x=>mon(x.tgl)===m),t)),backgroundColor:m6.map(m=>col(t,m===S.bln?"":"77"))}))},
options:{scales:{y:{ticks:{callback:short}}},plugins:{tooltip:{callbacks:{label:c=>" "+c.dataset.label+": "+rp(c.raw)}}},onClick:(e,el)=>el.length&&setBln(m6[el[0].index])}});
// tabel
const tb=rows.filter(x=>(S.tp==="all"||x.tipe===S.tp)&&(!S.kat||x.kategori===S.kat)&&x.kategori.toLowerCase().includes(S.q.toLowerCase())).sort((a,b)=>(a[S.sk]>b[S.sk]?1:-1)*S.sd);
$("#chip").innerHTML=S.kat?`<span class="chip" id="cx">${esc(S.kat)} ✕</span>`:"";
$("#tb").innerHTML=tb.length?tb.slice(0,100).map(x=>{const c=x.tipe==="masuk"?"in":"out";return `<tr><td>${x.tgl.slice(0,16)}</td><td>${esc(x.kategori)}</td><td class="${c}">${x.tipe}</td><td class="n ${c}">${c==="in"?"+":"-"}${rp(x.jumlah)}</td></tr>`}).join(""):'<tr><td colspan="4" class="empty">Tidak ada transaksi</td></tr>';
}

(async()=>{
try{if(DEMO){D=demo();$("#who").textContent="Pratinjau dengan data contoh"}
else{const r=await fetch("/api/"+location.pathname.split("/").pop());if(!r.ok)throw 0;const j=await r.json();D=j.trx;$("#who").textContent="Halo, "+j.nama}}
catch(e){document.body.innerHTML='<div class="wrap"><div class="card empty">Link dashboard tidak valid. Minta link baru lewat tombol Rekap di WhatsApp.</div></div>';return}
M=[...new Set(D.map(x=>mon(x.tgl)))].sort().reverse();
const t=new Date(),cm=t.getFullYear()+"-"+String(t.getMonth()+1).padStart(2,"0");S.bln=M.includes(cm)?cm:(M[0]||"all");
$("#bln").innerHTML='<option value="all">Semua bulan</option>'+M.map(m=>`<option value="${m}">${bname(m)}</option>`).join("");$("#bln").value=S.bln;
$("#bln").onchange=e=>setBln(e.target.value);
$("#prev").onclick=()=>{const m=M[M.indexOf(S.bln)+1];S.bln!=="all"&&m&&setBln(m)};
$("#next").onclick=()=>{const m=M[M.indexOf(S.bln)-1];S.bln!=="all"&&m&&setBln(m)};
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{S.tab=b.dataset.t;S.kat=null;S.tp="all";$("#tp").value="all";document.querySelectorAll(".tabs button").forEach(x=>x.classList.toggle("on",x===b));render()});
$("#leg").onclick=e=>{const li=e.target.closest(".li");li&&pick(li.dataset.k)};
$("#chip").onclick=()=>pick(S.kat);
$("#q").oninput=e=>{S.q=e.target.value;render()};
$("#tp").onchange=e=>{S.tp=e.target.value;render()};
document.querySelectorAll("th[data-s]").forEach(h=>h.onclick=()=>{const k=h.dataset.s;S.sd=S.sk===k?-S.sd:-1;S.sk=k;render()});
$("#th").onclick=()=>{const d=document.documentElement,dark=(d.dataset.theme||(matchMedia("(prefers-color-scheme:dark)").matches?"dark":"light"))==="dark";d.dataset.theme=dark?"light":"dark";render()};
render();
})();
