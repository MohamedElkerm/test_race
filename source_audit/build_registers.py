"""Rebuild provenance, template coverage and open-conflict registers from supplied source assets."""
import json,csv,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1]
base=R/'assets_original';out=R/'source_audit'
manifest=[]
for p in sorted(base.rglob('*')):
 if p.is_file():
  manifest.append({'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(out/'asset_manifest.json').write_text(json.dumps(manifest,indent=2))
# Content and backgrounds transcribed from governing TVG guide pp4-22, not prototype labels.
rows=[
('SFS001','SPORT PRESENTATION',4,'presentation',['sport','venue'],['HEADER_2LINES.TGA','SFS_2.tga']),
('SFS002','VENUE PRESENTATION',4,'presentation',['sport','venue'],['HEADER_2LINES.TGA','PRESENTATION.TGA','SFS_2.tga']),
('SFS003','SCHEDULE',5,'schedule',['sport','schedule'],['HEADER_2LINES.TGA','BAR_BASIC.TGA','FOOTER.TGA','SFS_2.tga']),
('SFS004','EVENT ID BY PHASE PRESENTATION',5,'presentation',['sport','event'],['HEADER_2LINES.TGA','SFS_2.tga']),
('SFS005','EVENT ID BY EVENT UNIT PRESENTATION',6,'presentation',['sport','event','heat'],['HEADER_2LINES.TGA','SFS_2.tga']),
('SFS200A','ATHLETE ID + LANE',7,'athlete',['athlete.name','lane'],['HEADER_1LINE.TGA','SFS_1.tga']),
('SFS200B','ATHLETE ID + FALSE START',7,'athlete',['athlete.name','lane','approved_irm'],['HEADER_1LINE.TGA','SHORT_BOX_RED.TGA','SFS_1.tga','DSQ.tga']),
('SFS200C','ATHLETE ID + QUALIFICATION + RECORD',8,'athlete',['athlete.name','lane','approved_qualification','approved_record'],['HEADER_1LINE.TGA','SHORT_BOX__LIGHT_BLUE.TGA','SFS_1.tga','Q.TGA']),
('SFS201A','TEAM ID + LANE',8,'team',['team.name','lane'],['HEADER_1LINE.TGA','SFS_1.tga']),
('SFS201B','TEAM ID + FALSE START',9,'team',['team.name','lane','approved_irm'],['HEADER_1LINE.TGA','SHORT_BOX_RED.TGA','SFS_1.tga','DSQ.tga']),
('SFS201C','TEAM ID + QUALIFICATION + RECORD',9,'team',['team.name','lane','approved_qualification','approved_record'],['HEADER_1LINE.TGA','SHORT_BOX__LIGHT_BLUE.TGA','SFS_1.tga','Q.TGA']),
('SFS202','TEAM LIST BY LANE',10,'relay_members',['team.name','members.name','members.position','time','lane'],['HEADER_1LINE_SHORT_NO_LOGO.TGA','BAR_BASIC_SHORT.TGA','FOOTER_SHORT.TGA','SHORT_BOX__LIGHT_BLUE.TGA','SFS_1.tga','Q.TGA']),
('SFS203A','START LIST INDIVIDUAL',10,'startlist',['sport','athlete.name','event','lane','country.flag'],['HEADER_2LINES.TGA','BAR_BASIC_WITH_BLUE.TGA','FOOTER.TGA','SFS_2.tga']),
('SFS203B','START LIST (RELAY)',11,'startlist',['sport','team.name','event','lane','country.flag'],['HEADER_2LINES.TGA','BAR_BASIC_WITH_BLUE.TGA','FOOTER.TGA','SFS_2.tga']),
('SFS204','LANE INDICATOR',11,'lane',['lane'],['FINISH.TGA']),
('SFS205A','NON COMPETITION AREA INDICATOR',12,'area',['WARM UP POOL'],['SHORT_BOX_LIGHT_BLUE.TGA']),
('SFS205B','NON COMPETITION AREA INDICATOR',12,'area',['CALL ROOM'],['SHORT_BOX_LIGHT_BLUE.TGA']),
('SFS206','ATHLETE + UNIVERSITY',13,'university',['athlete.name','athlete.university','lane','country.flag'],['HEADER_2LINES.TGA','SFS_2.tga']),
('SFS300A','INDIVIDUAL WINNER',14,'winner',['athlete.name','event','approved_winner'],['HEADER_2LINES.TGA','SFS_2.tga']),
('SFS300B','RELAY WINNER',14,'winner',['team.name','event','approved_winner'],['HEADER_2LINES.TGA','SFS_2.tga']),
('SFS301A','ADVANCE TO PHASE INDIVIDUAL',15,'qualification',['sport','event','athlete.name','rank','time','approved_qualification'],['HEADER_2LINES.TGA','BAR_BASIC_WITH_BLUE.TGA','FOOTER.TGA','SFS_2.tga']),
('SFS301B','ADVANCE TO PHASE RELAY',15,'qualification',['sport','event','team.name','rank','time','approved_qualification'],['HEADER_2LINES.TGA','BAR_BASIC_WITH_BLUE.TGA','FOOTER.TGA','SFS_2.tga']),
('SFS302A','RESULTS INDIVIDUAL',16,'results',['sport','event','athlete.name','rank','time','status'],['HEADER_2LINES.TGA','BAR_BASIC_WITH_BLUE.TGA','FOOTER.TGA','SFS_2.tga']),
('SFS302B','RESULTS RELAY',16,'results',['sport','event','team.name','rank','time','status'],['HEADER_2LINES.TGA','BAR_BASIC_WITH_BLUE.TGA','FOOTER.TGA','SFS_2.tga']),
('SFS500','RACE CLOCK',17,'clock',['running_time'],['SFS_CLOCK.TGA']),
('SFS501','RACE CLOCK BEFORE SPLINT POINT',17,'clock',['running_time','distance','split_time'],['SFS_CLOCK.TGA','FINISH.TGA','BLUE_RECORDS_BOX.TGA']),
('SFS502','RACE CLOCK BEFORE FINISH',18,'clock',['running_time','approved_records'],['SFS_CLOCK.TGA','BLUE_RECORDS_BOX.TGA']),
('SFS503','RACE CLOCK AT FINISH',18,'clock',['finish_time','approved_records','lane'],['SFS_CLOCK.TGA','FINISH.TGA','BLUE_RECORDS_BOX.TGA','LANE_BOX.TGA']),
('SFS504A','RACE CLOCK AT SPLIT POINT + STANDINGS',19,'standings',['running_time','distance','lane','athlete.name','split_time'],['SFS_CLOCK.TGA','FINISH.TGA','SHORT_BOX3_FIRST.TGA','SHORT_BOX3_GREEN.TGA','SHORT_BOX_CLOCK.TGA','BAR_STANDING_RANK.TGA']),
('SFS504B','RACE CLOCK AT SPLIT POINT + STANDINGS (RELAYS)',19,'standings',['running_time','distance','lane','team.name','split_time'],['SFS_CLOCK.TGA','FINISH.TGA','SHORT_BOX3_FIRST.TGA','SHORT_BOX3_RED.TGA','SHORT_BOX_CLOCK.TGA','BAR_STANDING_RANK.TGA']),
('SFS900','VICTORY CEREMONY',20,'presentation',['sport','event','VICTORY CEREMONY'],['HEADER_2LINES.TGA','SFS_2.tga']),
('SFS901A','INDIVIDUAL MEDAL',20,'medal',['athlete.name','event','approved_medal'],['HEADER_1LINE.TGA','SFS_2.tga','MEDAL_GOLD_B.TGA','MEDAL_SILVER_B.TGA','MEDAL_BRONZE_B.TGA']),
('SFS901B','INDIVIDUAL MEDAL RELAY',21,'medal',['athlete.name','team.name','event','approved_medal'],['HEADER_1LINE.TGA','BAR_BASIC.TGA','FOOTER.TGA','SFS_1.tga','MEDAL_GOLD_B.TGA','MEDAL_SILVER_B.TGA','MEDAL_BRONZE_B.TGA']),
('SFS902A','MEDALS LIST',21,'medals',['sport','event','athlete.name','approved_medal'],['HEADER_2LINES.TGA','BAR_BASIC.TGA','FOOTER.TGA','SFS_2.tga','MEDAL_GOLD.TGA','MEDAL_SILVER.TGA','MEDAL_BRONZE.TGA']),
('SFS902B','MEDALS LIST RELAY',22,'medals',['sport','event','team.name','approved_medal'],['HEADER_2LINES.TGA','BAR_BASIC.TGA','FOOTER.TGA','SFS_2.tga','MEDAL_GOLD.TGA','MEDAL_SILVER.TGA','MEDAL_BRONZE.TGA'])]
assets={p.name.lower():str(p.relative_to(R)) for p in (base/'tga').rglob('*.tga')}
aliases={'header_2lines.tga':'header2_lines.tga','header_1line.tga':'header1_line.tga','header_1line_short_no_logo.tga':'header1_short_no_logo.tga','short_box__light_blue.tga':'short_box_light_blue.tga','footer_short.tga':'footer short.tga'}
registry={};missing=[]
for code,name,page,kind,fields,required in rows:
 mappings=[];absent=[]
 for a in required:
  key=a.lower();mapped=aliases.get(key,key);p=assets.get(mapped)
  mappings.append({'guide_name':a,'original':p,'processed':'/assets/sfs/'+Path(mapped).stem.replace(' ','_')+'.png' if p else None,'resolution':'EXACT_NAME_CASE_NORMALISED' if key==mapped and p else 'DOCUMENTED_FILENAME_VARIANT_PENDING_CONFIRMATION' if p else 'ASSET MISSING'})
  if not p:absent.append(a);missing.append({'template':code,'asset':a,'status':'ASSET MISSING / NOT APPROVED','candidate':'HD/background/CSP_clock.tga' if a=='SFS_CLOCK.TGA' else '', 'action':'Supplier/FISU written confirmation required. No automatic substitution.'})
 refs=sorted((base/'references').glob(code+' - *'))
 registry[code]={'code':code,'name':name,'guide_page':page,'kind':kind,'fields':fields,'assets':mappings,'missing':absent,'reference':'/references/'+refs[0].name if refs else None,
 'component':'renderTemplate('+code+')','implemented':'ENGINEERING COMPONENT','approval_status':'ASSET MISSING / NOT APPROVED' if absent else 'AWAITING VISUAL QA AND FISU APPROVAL','visually_matched':False,'production_approved':False,
 'state_behaviour':'Results label follows actual status. Qualification, record, winner and medal fields require documented Jury adjudication. Stale LIVE timing is suppressed. VENUE TAKE blocked until production approval.',
 'preview_url':'/broadcast_tvg/?template='+code+'&preview=1','test_case':'browser capture + field/state gate + independent visual comparison; see testing reports'}
(R/'templates_sfs/registry.json').write_text(json.dumps(registry,indent=2))
with (out/'Template_Coverage_Matrix.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['code','name','guide_page','kind','approval_status','visually_matched','production_approved','missing','reference']);w.writeheader()
 for d in registry.values():w.writerow({k:('; '.join(d[k]) if isinstance(d[k],list) else d[k]) for k in w.fieldnames})
with (out/'Missing_Assets_Register.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['template','asset','status','candidate','action']);w.writeheader();w.writerows(missing)
conflicts=[
 ('SRC-01','TVG guide / TGA archive','BAR_BASIC_WITH_BLUE.TGA absent','All start/result list templates blocked; bar_basic is not substituted','FISU TV production / artwork supplier'),
 ('SRC-02','TVG guide / TGA archive','SFS_CLOCK vs CSP_clock','Candidate retained but never aliased automatically','FISU TV production / artwork supplier'),
 ('SRC-03','TVG guide / TGA archive','header/underscore/space filename variants','Geometry-compatible mappings documented, confirmation pending','Artwork supplier'),
 ('SRC-04','TVG guide / JPG','SFS001/002 presentation examples differ from content/background descriptions','Exact presentation artwork needs independent approval','FISU TV production'),
 ('SRC-05','TVG guide / archive','Medal icons absent; some examples use 2025 university wording','No replacement icons or legacy championship text are generated','FISU TV production'),
 ('SRC-06','Common fonts / JPG','Lato fonts available, exact weight/size/baseline not specified for every data field','Use supplied Lato; typography still requires measured QA','FISU TV production'),
 ('SRC-07','Technology Guidelines 2025 p15 / proposed custom web distribution','OC-developed public results distribution not accepted in guideline','Local engineering API only; provider/FISU acceptance needed before public deployment','FISU Technology / appointed Results Provider'),
 ('SRC-08','SwimTime manual p31 / p32','Summary says video 9600; interface description says standard 19200','Configurable baud; 19200 profile per section 5.1.1.2; actual device settings must be confirmed','ALGE timing supplier'),
 ('SRC-09','ALGE manual p32 / p33','RR rank omitted above 14xx; START from 14xx; actual firmware not supplied','Separate strict parsers, no automatic guessing','ALGE timing supplier'),
 ('SRC-10','Older catalogues / October programme','April legacy; catalogue window starts 27 Oct while programme arrivals start 25 Oct','Use 25-30 Oct programme; competition 28-29 Oct; no per-race times inferred from session start','Competition Manager'),
 ('SRC-11','Extra JPG reference / guide index','SFS006 RECORDS JPG not listed in governing guide index','Retained in archive, not treated as an approved required template','FISU TV production')]
with (out/'Source_Conflict_Register.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['id','sources','conflict','treatment','owner']);w.writerows(conflicts)
summary={'date':'2026-10-20','templates':len(registry),'templates_with_missing_assets':sum(bool(x['missing']) for x in registry.values()),'fully_matched':0,'production_approved':0,'original_assets_hashed':len(manifest),'wipe':{'status':'NOT DOWNLOADED / NOT INSPECTED','bytes':299682423,'connector_limit':268435456,'action':'Supply extracted files or split archive parts under 256 MiB'},'prototype_review':{'v03':'standard-library demo; no authenticated results approval or actual serial integration','v04':'same demo architecture; fixed sizes','v05':'engineering prototype independently inspected; not production approved; its fallback substitutions are not adopted'},'source_scope':'Root and technical source folders inventoried. Specified TVG/prototype archives inspected. Catalogues extracted (24/22/21 slides). Unrelated passport/finance folders not downloaded. No real roster or device log imported.'}
(out/'Source_Audit.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
