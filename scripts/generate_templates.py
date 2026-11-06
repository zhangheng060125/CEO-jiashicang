"""Generate downloadable templates and documentation from the backend validation schema."""
from pathlib import Path
import csv,json,sys
from openpyxl import Workbook
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import server
wb=Workbook();wb.remove(wb.active)
lines=['# 导入字段字典','', '各类型文件使用 UTF-8 CSV 或 Excel .xlsx，列顺序与模板一致。每批固定归属一个项目与一个数据集。多工作表合集用于查阅；实际导入请下载单类型模板或将目标工作表另存为单表文件。','', 'external_id 为必填稳定业务编号。同类型、同数据集、同项目、同编号且内容一致会跳过；内容改变须显式编辑。数字不含千分位，可选金额留空表示未知；日期 YYYY-MM-DD，布尔 true/false。','']
for kind,schema in server.SCHEMAS.items():
 header=['external_id',*schema['fields']]
 with open(ROOT/'templates'/(kind+'.csv'),'w',encoding='utf-8-sig',newline='') as out:csv.writer(out).writerow(header)
 ws=wb.create_sheet(kind);ws.append(header)
 lines.extend(['## '+schema['label']+' / '+kind,'','|字段|说明|类型|必填|枚举|','|---|---|---|---|---|','|external_id|稳定外部编号|text|是||'])
 for k,v in schema['fields'].items():lines.append('|'+ '|'.join([k,v['label'],v['type'],'是' if v['required'] else '否',', '.join(v['options'] or [])])+'|')
 lines.append('')
wb.save(ROOT/'templates/all-templates.xlsx')
(ROOT/'docs/import-schema.md').write_text('\n'.join(lines),encoding='utf8')
(ROOT/'docs/schema.json').write_text(json.dumps(server.SCHEMAS,ensure_ascii=False,indent=2),encoding='utf8')
print(f'Generated {len(server.SCHEMAS)} CSV templates, Excel workbook and schema documentation.')
