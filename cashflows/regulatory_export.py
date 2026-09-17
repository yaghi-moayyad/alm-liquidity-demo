"""Template-preserving XLSX exports for the regulatory report workbenches."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET
from django.conf import settings

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
ET.register_namespace('',NS)

def _cell(root, address):
    for cell in root.findall(f'.//{{{NS}}}c'):
        if cell.get('r') == address:
            return cell
    raise KeyError(address)

def _set_number(root,address,value):
    cell=_cell(root,address);cell.attrib.pop('t',None)
    node=cell.find(f'{{{NS}}}v')
    if node is None: node=ET.SubElement(cell,f'{{{NS}}}v')
    node.text=str(value)

def _shared_strings(archive):
    if 'xl/sharedStrings.xml' not in archive.namelist(): return []
    root=ET.fromstring(archive.read('xl/sharedStrings.xml'))
    return [''.join(node.text or '' for node in item.findall(f'.//{{{NS}}}t')) for item in root.findall(f'{{{NS}}}si')]

def _cell_value(cell,shared):
    value=cell.find(f'{{{NS}}}v')
    if value is None:return ''
    return shared[int(value.text)] if cell.get('t')=='s' else value.text

def _serialize_template(template_name, mutate):
    template=Path(settings.BASE_DIR)/'cashflows'/'report_templates'/template_name
    with ZipFile(template) as source:
        files={name:source.read(name) for name in source.namelist()}
    root=ET.fromstring(files['xl/worksheets/sheet1.xml']);mutate(root,files)
    workbook=ET.fromstring(files['xl/workbook.xml']);calc=workbook.find(f'.//{{{NS}}}calcPr')
    if calc is None:calc=ET.SubElement(workbook,f'{{{NS}}}calcPr')
    calc.set('calcMode','auto');calc.set('fullCalcOnLoad','1');calc.set('forceFullCalc','1')
    files['xl/worksheets/sheet1.xml']=ET.tostring(root,encoding='utf-8',xml_declaration=True);files['xl/workbook.xml']=ET.tostring(workbook,encoding='utf-8',xml_declaration=True)
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as destination:
        for name,content in files.items(): destination.writestr(name,content)
    return output.getvalue()

def lcr_xlsx(report,positions):
    by_key={row.get('key'):row for row in positions}
    cells={'coins':'C3','reserves':'C4','sovereign':'C5','level2a':'C7','equities':'C11','retail_stable':'C19','retail_savings':'C20','retail_time':'C21','bank_operational':'C22','intergroup':'C23','wholesale':'C46','repo':'C54','contingent':'C63','customer_inflows':'C82','financial_inflows':'C86'}
    def mutate(root,_files):
        for key,address in cells.items(): _set_number(root,address,by_key.get(key,{}).get('balance',0))
    return _serialize_template('lcr_template.xlsx',mutate)

def nsfr_xlsx(lines):
    def mutate(root,files):
        shared=_shared_strings(ZipFile(BytesIO(b''))) if False else []
        # Codes are stored as normal text/numbers in the supplied template.
        with ZipFile(Path(settings.BASE_DIR)/'cashflows'/'report_templates'/'nsfr_template.xlsx') as archive: shared=_shared_strings(archive)
        by_code={}
        for cell in root.findall(f'.//{{{NS}}}c'):
            address=cell.get('r','')
            if address.startswith('A'):
                value=_cell_value(cell,shared)
                if value: by_code[str(value)]=address[1:]
        for line in lines:
            row=by_code.get(str(line.get('code','')))
            if not row: continue
            for start,field in ((3,'jod'),(6,'usd'),(9,'other'),(16,'factors')):
                values=line.get(field,[0,0,0])
                for offset,value in enumerate(values):
                    _set_number(root,f'{chr(64+start+offset)}{row}',value)
    return _serialize_template('nsfr_template.xlsx',mutate)
