'use strict';
function renderImageMap(container,layout,availability,interactive,onRegion=null,selectedId=null) {
  const ns='http://www.w3.org/2000/svg',editable=typeof onRegion==='function';
  const regions=layout.elements.filter(r=>editable||['seat','zone'].includes(r.kind));
  const key=JSON.stringify([layout.columns,layout.rows,layout.image_url,layout.detector,editable,regions.map(r=>[r.id,r.kind,r.seat_id,r.points||r.runs])]);
  let view=container._imageMapView;
  if(!view||view.key!==key||view.svg.parentNode!==container){
    const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${layout.columns} ${layout.rows}`);svg.setAttribute('class','image-seat-map');svg.setAttribute('aria-label','Sơ đồ phòng');
    const image=document.createElementNS(ns,'image');image.setAttribute('href',layout.image_url);image.setAttribute('width',layout.columns);image.setAttribute('height',layout.rows);svg.append(image);
    const rows=new Map(),alternatives=document.createElement('div');alternatives.className='image-map-options';alternatives.setAttribute('aria-label','Danh sách phòng');
    for(const region of regions){
      const path=document.createElementNS(ns,'path');path.setAttribute('d',region.points?region.points.map(([x,y],i)=>`${i?'L':'M'}${x} ${y}`).join('')+'Z':region.runs.map(([y,x,end])=>`M${x} ${y}h${end-x}v1h-${end-x}Z`).join(''));
      path.setAttribute('data-region-id',region.id);path.setAttribute('role','button');const title=document.createElementNS(ns,'title');path.append(title);svg.append(path);
      let button=null;if(!editable){button=document.createElement('button');button.type='button';alternatives.append(button);}
      rows.set(region.id,{path,title,button});
    }
    container.replaceChildren(svg);if(!editable)container.append(alternatives);
    view={key,svg,rows};container._imageMapView=view;
    container.style.width='100%';container.style.height='auto';container.style.position='relative';
  }
  const attr=(node,name,value)=>{if(node.getAttribute(name)!==String(value))node.setAttribute(name,String(value));};
  const items=new Map((availability?.items||[]).map(item=>[item.id,item]));
  for(const region of regions){
    const {path,title,button}=view.rows.get(region.id),item=items.get(region.seat_id);
    const own=typeof held!=='undefined'&&held?.seat_id===region.seat_id&&held?.session_id===$('session').value;
    const picked=editable?selectedId===region.id:typeof selectedSeat!=='undefined'&&selectedSeat?.id===region.seat_id;
    const available=editable||!!(interactive&&item?.available),label=region.label||region.seat_code||region.id;
    const status=editable?(region.kind==='decoration'?'Không cho đăng kí':`Phòng, ${region.capacity||'chưa nhập'} người`):own?'Bạn đang giữ một suất':`Còn ${item?.remaining??(item?.available?1:0)}/${item?.capacity??region.capacity??1} chỗ`;
    attr(path,'class',`image-map-region ${region.kind}${layout.detector==='quadrilateral-v1'?' room':''}${picked?' picked':''}${own?' own-hold':''}${!available?' unavailable':''}`);
    attr(path,'tabindex',available?'0':'-1');attr(path,'aria-disabled',!available);attr(path,'aria-pressed',!!picked);attr(path,'aria-label',`${label}: ${status}`);
    if(title.textContent!==`${label}: ${status}`)title.textContent=`${label}: ${status}`;
    const activate=()=>{if(!available)return;if(editable)onRegion(region);else{selectedSeat={id:region.seat_id,seat_code:label};renderImageMap(container,layout,availability,interactive);updateSummary();}};
    path.onclick=activate;path.onkeydown=event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();activate();}};
    if(button){
      button.disabled=!available;button.className='image-map-option'+(picked?' picked':'');attr(button,'aria-pressed',!!picked);
      if(button.textContent!==`${label} · ${status}`)button.textContent=`${label} · ${status}`;button.onclick=activate;
    }
  }
}
