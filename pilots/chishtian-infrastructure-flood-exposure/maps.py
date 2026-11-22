"""Render water and sewerage flood-exposure maps in the UCRA report style."""
from pathlib import Path
import math
import re
import textwrap

import geopandas as gpd
import numpy as np
import pandas as pd
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle
from matplotlib.font_manager import FontProperties
from shapely.geometry import box
import pymupdf

from flood_exposure import load_hazards

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs'
CACHE = ROOT / 'inputs/basemap'
FONT = CACHE / 'UCRAHelvetica-Regular.ttf'
font_manager.fontManager.addfont(str(FONT))
FONTNAME = FontProperties(fname=FONT).get_name()
plt.rcParams.update({'font.family': FONTNAME, 'font.size': 9, 'pdf.fonttype': 42})
INK='#30363b';RED='#d33e3c';FLOOD='#999add';BOUNDARY='#555555'
FRAME_W=251.28;FRAME_H=168.264

def read_existing():
    gpkg=OUT/'exposure.gpkg'
    layers={k:gpd.read_file(gpkg,layer=k).to_crs(3857)
            for k in ['water_lines','water_points','sewer_lines','sewer_points']}
    boundary=gpd.read_file(gpkg,layer='client_proposed_mc_boundary').to_crs(3857)
    scan=gpd.read_file(gpkg,layer='existing_city_scan_aoi').to_crs(3857)
    hazards,footprints,meta=load_hazards()
    cv=lambda g:gpd.GeoSeries([g],crs=32643).to_crs(3857).iloc[0]
    hazards={k:cv(v) for k,v in hazards.items()}
    footprints={k:cv(v) for k,v in footprints.items()}
    return layers,boundary,scan,hazards,footprints,meta


def basemap(bounds):
    tiles={}
    for p in CACHE.glob('*.png'):
        m=re.fullmatch(r'(\d+)_(\d+)_(\d+)\.png',p.name)
        if m:tiles[tuple(map(int,m.groups()))]=p
    R=20037508.342789244;z=14;n=2**z;span=2*R/n
    x0,y0,x1,y1=bounds
    xa,xb=math.floor((x0+R)/span),math.floor((x1+R)/span)
    ya,yb=math.floor((R-y1)/span),math.floor((R-y0)/span)
    needed=[(z,x,y) for x in range(xa,xb+1) for y in range(ya,yb+1)]
    if not (all(t in tiles for t in needed)):
        raise ValueError('Same-provider basemap tiles are incomplete')
    img=Image.new('RGB',((xb-xa+1)*256,(yb-ya+1)*256),'white')
    for t in needed:
        p=tiles[t];im=Image.open(p)
        if not (im.size==(256,256)):
            raise ValueError('Validation failed: im.size==(256,256)')
        img.paste(im.convert('RGB'),((t[1]-xa)*256,(t[2]-ya)*256))
    return np.asarray(img),(-R+xa*span,-R+(xb+1)*span,R-(yb+1)*span,R-ya*span)


def draw_key(ax,sector):
    ax.set_xlim(0,1);ax.set_ylim(0,1);ax.axis('off')
    y=.945
    def entry(label,kind,color=INK,marker='o',linestyle='-'):
        nonlocal y
        lines=textwrap.wrap(label,19)
        if kind=='patch':ax.add_patch(Rectangle((.09,y-.015),.14,.026,facecolor=color,edgecolor='none'))
        elif kind=='line':ax.plot([.09,.23],[y,y],color=color,lw=1.4,linestyle=linestyle)
        elif kind=='hatch':ax.add_patch(Rectangle((.09,y-.015),.14,.026,facecolor='#f1f1ee',edgecolor='#aaaaaa',hatch='////',lw=.3))
        else:ax.plot([.16],[y],marker=marker,ms=4.5,mfc=color if color==RED else 'white',mec=INK,mew=.6,color=INK,linestyle='none')
        ax.text(.30,y+.012,'\n'.join(lines),fontsize=7.8,color=INK,va='top',linespacing=1.1)
        y-=.044+.024*(len(lines)-1)
    entry('Mapped flood zone','patch',FLOOD)
    entry('Supplied network','line')
    entry('Network in flood zone','line',RED)
    entry('Facility in flood zone','point',RED)
    entry('Boundary','line',BOUNDARY)
    entry('City Scan study area','line','#777777',linestyle=':')
    entry('Outside flood extent','hatch')
    y-=.006
    ax.text(.09,y,'Facilities',fontsize=8.7,color=INK);y-=.042
    if sector=='water':
        for label,marker in [('Tube well','o'),('Ground storage tank','s'),('Overhead reservoir','^'),('Labelled non-functional','x')]:entry(label,'point',marker=marker)
    else:
        for label,marker in [('Disposal station','D'),('Outfall chamber','v')]:entry(label,'point',marker=marker)
    if not (y>.015):
        raise ValueError(('legend too long',sector,y))
    # Align the visible key content exactly with the bottom of the map frame.
    ax.figure.canvas.draw()
    renderer=ax.figure.canvas.get_renderer()
    artists=[*ax.texts,*ax.lines,*ax.patches]
    bottom=min(artist.get_window_extent(renderer).y0 for artist in artists)
    offset=-ax.transAxes.inverted().transform((0,bottom))[1]
    for label in ax.texts:
        x,yy=label.get_position();label.set_position((x,yy+offset))
    for line in ax.lines:
        line.set_ydata(np.asarray(line.get_ydata())+offset)
    for patch in ax.patches:
        patch.set_y(patch.get_y()+offset)


def panel(sector,ft,rp,layers,boundary,scan,hazards,footprints,bounds,bg,extent):
    fig=plt.figure(figsize=(2255/300,1510/300),facecolor='white')
    # The map follows the original City Scan 8.77/7.55 map-area ratio; the
    # right column holds the borderless legend, aligned at the bottom.
    map_width=.735;height=map_width*(2255/1510)/(8.77/7.55)
    ax=fig.add_axes([.012,(1-height)/2,map_width,height])
    legend=fig.add_axes([.767,(1-height)/2,.225,.93]);draw_key(legend,sector)
    ax.imshow(bg,extent=extent,origin='upper',interpolation='bilinear',zorder=0)
    view=box(*bounds)
    outside=view.difference(footprints[ft])
    gpd.GeoSeries([outside],crs=3857).plot(ax=ax,facecolor='#f3f3ef',edgecolor='#c5c5bd',hatch='////',lw=.15,alpha=.65,zorder=1)
    if not hazards[ft,rp].is_empty:
        gpd.GeoSeries([hazards[ft,rp]],crs=3857).plot(ax=ax,color=FLOOD,alpha=.68,lw=0,zorder=2)
    scan.boundary.plot(ax=ax,color='#777777',lw=.55,linestyle=':',zorder=3)
    boundary.boundary.plot(ax=ax,color=BOUNDARY,lw=.7,zorder=4)
    g=layers[f'{sector}_lines'];p=layers[f'{sector}_points']
    g.plot(ax=ax,color=INK,lw=.6,zorder=5)
    seg=g.geometry.intersection(hazards[ft,rp]);seg=seg[seg.length>1e-7]
    if len(seg):seg.plot(ax=ax,color=RED,lw=1.1,zorder=6)
    for typ,pts in p.groupby('Type'):
        marker=('s' if 'GST' in typ else '^' if 'OHR' in typ else 'o') if sector=='water' else ('D' if 'Station' in typ else 'v')
        ax.scatter(pts.geometry.x,pts.geometry.y,marker=marker,s=14 if sector=='water' else 22,
                   c=np.where(pts[f'{ft}_{rp}_exposed']>0,RED,'white'),edgecolors=INK,linewidths=.5,zorder=7)
        if 'Non' in typ:ax.scatter(pts.geometry.x,pts.geometry.y,marker='x',s=13,color=INK,lw=.5,zorder=8)
    x0,y0,x1,y1=bounds;w=x1-x0;h=y1-y0
    # Match City Scan's north arrow at bottom right and metric scale at bottom left.
    xx=x0+w*.945;yy=y0+h*.06
    ax.annotate('',xy=(xx,yy+h*.065),xytext=(xx,yy),arrowprops=dict(arrowstyle='-|>',lw=.65,color=INK),zorder=9)
    ax.text(xx,yy-h*.019,'N',fontsize=6,color=INK,ha='center',zorder=9)
    midlat=29.8;scale=2000/math.cos(math.radians(midlat));sx=x0+w*.05;sy=y0+h*.04
    ax.plot([sx,sx+scale],[sy,sy],color=INK,lw=.7,zorder=9)
    for x in [sx,sx+scale/2,sx+scale]:ax.plot([x,x],[sy-h*.004,sy+h*.004],color=INK,lw=.5,zorder=9)
    for x,label in [(sx,'0'),(sx+scale/2,'1'),(sx+scale,'2 km')]:ax.text(x,sy+h*.01,label,fontsize=6,color=INK,ha='center',zorder=9)
    ax.text(x0+w*.02,y0+h*.965,f'1-in-{rp:,} year',fontsize=8,color=INK,
            bbox=dict(facecolor='white',edgecolor='none',alpha=.85,pad=2),zorder=10)
    ax.set_xlim(x0,x1);ax.set_ylim(y0,y1);ax.set_aspect('equal');ax.set_xticks([]);ax.set_yticks([])
    for sp in ax.spines.values():sp.set_visible(False)
    path=OUT/f'Chishtian_{sector}_{ft}_r{rp}_UCRA.png'
    fig.savefig(path,dpi=300,facecolor='white');plt.close(fig)
    return path


def text(page,rect,body,size=9,color=(.13,.13,.13),align=0):
    page.insert_font(fontname='UCRA',fontfile=str(FONT))
    remaining=page.insert_textbox(pymupdf.Rect(rect),body,fontname='UCRA',fontsize=size,color=color,align=align)
    if not (remaining>=0):
        raise ValueError(('text overflow',body[:65],remaining))


def header(page,sector):
    page.insert_font(fontname='UCRA',fontfile=str(FONT))
    # Same heading sizes, accent and letter page dimensions as the report.
    page.insert_text((48.96,42),'RISK IDENTIFICATION',fontname='UCRA',fontsize=19,color=(.38,.40,.42),render_mode=1,border_width=.03)
    page.insert_text((48.96,59),'Flood Hazards',fontname='UCRA',fontsize=15,color=(.13,.13,.13))
    page.draw_line((48.96,73.8),(563.04,73.8),color=(110/255,164/255,207/255),width=1)
    title='Chishtian: water infrastructure' if sector=='water' else 'Chishtian: sewerage and sanitation infrastructure'
    page.insert_text((48.96,91),title,fontname='UCRA',fontsize=11,color=(.13,.13,.13))


def compose(paths,summary):
    doc=pymupdf.open();large=pymupdf.open()
    frame_records=[]
    for sector in ['water','sewer']:
        page=doc.new_page(width=612,height=792);header(page,sector)
        for row,rp in enumerate([10,100,1000]):
            y=132.08+row*191
            for col,(ft,label) in enumerate([('fluvial','River'),('pluvial','Rainwater')]):
                x=48.96+col*262.8
                text(page,(x,y-16,x+FRAME_W,y-2),f'{label} flooding | 1-in-{rp:,} year',size=8.2)
                rect=pymupdf.Rect(x,y,x+FRAME_W,y+FRAME_H)
                page.insert_image(rect,filename=str(paths[sector,ft,rp]),keep_proportion=False)
                frame_records.append(dict(sector=sector,hazard=ft,rp=rp,bbox=list(rect),width=rect.width,height=rect.height))
                a=summary[(summary.layer==f'{sector}_lines')&(summary.hazard==ft)&(summary.return_period_years==rp)].iloc[0]
                p=summary[(summary.layer==f'{sector}_points')&(summary.hazard==ft)&(summary.return_period_years==rp)].iloc[0]
                # Enlarged view keeps exactly the same panel, with a readable legend.
                lp=large.new_page(width=612,height=792);header(lp,sector)
                text(lp,(48.96,119,563.04,139),f'{label} flooding | 1-in-{rp:,} year | 2020 baseline',size=11)
                lp.insert_image(pymupdf.Rect(48.96,146,563.04,146+514.08*1510/2255),filename=str(paths[sector,ft,rp]))
                text(lp,(48.96,505,563.04,527),f'Mapped network overlap: {a.mapped_exposed:.2f} / {a.supplied_total:.2f} km. Facilities: {int(p.mapped_exposed)} / {int(p.supplied_total)}.',size=9)
    for d in [doc,large]:d.set_metadata({'title':'Chishtian infrastructure flood exposure — UCRA report style','author':'UCRA','subject':'Water and sewerage infrastructure intersected with 2020 flood footprints','creationDate':'','modDate':''})
    main=OUT/'maps.pdf'
    doc.save(main,garbage=4,deflate=True);large.save(OUT/'maps_enlarged.pdf',garbage=4,deflate=True)
    doc.close();large.close()
    return main,frame_records


def render_maps():
    """Draw the map sheets; discard temporary panel images after composition."""
    global OUT
    import tempfile
    layers, boundary, scan, hazards, footprints, _ = read_existing()
    x0,y0,x1,y1=boundary.geometry.union_all().union(layers['water_points'].geometry.union_all()).bounds
    cx,cy=(x0+x1)/2,(y0+y1)/2;w,h=x1-x0,y1-y0;ratio=8.77/7.55
    w=max(w,h*ratio);h=w/ratio;bounds=(cx-w*.525,cy-h*.525,cx+w*.525,cy+h*.525)
    summary=pd.read_csv(OUT/'exposure.csv')
    output_folder=OUT
    with tempfile.TemporaryDirectory(prefix='chishtian-maps-') as work:
        try:
            OUT=Path(work)
            bg,extent=basemap(bounds)
            paths={(sector,ft,rp):panel(sector,ft,rp,layers,boundary,scan,hazards,footprints,bounds,bg,extent)
                   for sector in ['water','sewer'] for rp in [10,100,1000] for ft in ['fluvial','pluvial']}
            OUT=output_folder
            compose(paths,summary)
        finally:
            OUT=output_folder
