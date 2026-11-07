"""Local document recognition and review suggestions. Never posts accounting entries."""
from datetime import date
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from PIL import Image,ImageOps
from openpyxl import load_workbook
try:
 from pillow_heif import register_heif_opener
 register_heif_opener();HEIC_READY=True
except ImportError:HEIC_READY=False

def capability(data):
 model=Path(data)/'ocr/tessdata'
 return {'engine':'local_ocr','available':bool(shutil.which('tesseract')),
         'chinese_ready':(model/'chi_sim.traineddata').is_file(),
         'pdf_available':bool(shutil.which('pdftotext')),'heic_available':HEIC_READY,'external_ai':False}

def run(args,timeout=25):
 result=subprocess.run(args,capture_output=True,timeout=timeout,check=False)
 if result.returncode:raise ValueError('文件无法识别，请补拍清晰照片或交财务核对')
 return result.stdout.decode('utf-8',errors='replace')[:40000]

def image_text(path,data):
 if not shutil.which('tesseract'):raise ValueError('本机OCR尚未安装；文件已归档，等待人工核对')
 with tempfile.TemporaryDirectory(prefix='senhuo-ocr-') as temp:
  image=ImageOps.exif_transpose(Image.open(path));image.thumbnail((2600,2600));image.convert('RGB').save(Path(temp)/'page.png')
  model=Path(data)/'ocr/tessdata';args=['tesseract',str(Path(temp)/'page.png'),'stdout','--psm','6']
  if (model/'chi_sim.traineddata').is_file() and (model/'eng.traineddata').is_file():args+=['--tessdata-dir',str(model),'-l','chi_sim+eng']
  else:args+=['-l','eng']
  return run(args)

def document_text(path,mime,data):
 if mime.startswith('image/'):return image_text(path,data)
 if mime=='application/pdf':
  if not shutil.which('pdftotext'):raise ValueError('PDF识别组件未安装；文件已归档，等待人工核对')
  text=run(['pdftotext','-f','1','-l','3','-layout',str(path),'-'])
  if len(re.sub(r'\s','',text))>=30:return text
  executable='/usr/bin/pdftoppm' if Path('/usr/bin/pdftoppm').exists() else shutil.which('pdftoppm')
  if not executable:raise ValueError('扫描PDF需补装图片识别组件，或拍照上传')
  with tempfile.TemporaryDirectory(prefix='senhuo-pdf-') as temp:
   run([executable,'-f','1','-l','3','-scale-to','2400','-png',str(path),str(Path(temp)/'page')],timeout=45)
   return '\n'.join(image_text(p,data) for p in sorted(Path(temp).glob('page-*.png')))[:40000]
 if mime=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
  wb=load_workbook(path,read_only=True,data_only=False)
  try:
   lines=[]
   for ws in list(wb)[:3]:
    for i,row in enumerate(ws.iter_rows(max_col=25,values_only=True)):
     if i>=300:break
     lines.append(' '.join(str(v) for v in row if v is not None and not str(v).startswith('=')))
   return '\n'.join(lines)[:40000]
  finally:wb.close()
 raise ValueError('此附件仅归档，不支持单据识别')

def suggest(text):
 lines=[re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])','',line).strip() for line in text.splitlines()]
 clean='\n'.join(lines)
 fields={'amount':None,'day':None,'merchant':'','invoice_number':'','category':'other','document_class':'unknown'}
 warnings=[]
 found=re.search(r'(20\d{2})\s*[年/.-]\s*(\d{1,2})\s*[月/.-]\s*(\d{1,2})',clean)
 if found:
  try:fields['day']=date(*map(int,found.groups())).isoformat()
  except ValueError:pass
 for labels in [('价税合计','小写','TOTAL'),('合计','总金额','应付'),('金额','AMOUNT')]:
  amounts=[]
  for i,line in enumerate(lines):
   if any(label.lower() in line.lower() for label in labels):
    candidates=re.findall(r'(?<!\d)(?:[¥￥$]\s*)?([0-9]{1,7}(?:[,，][0-9]{3})*\.[0-9]{1,2})(?!\d)',line)
    if not candidates and i+1<len(lines):candidates=re.findall(r'[¥￥$]\s*([0-9]{1,7}\.[0-9]{1,2})',lines[i+1])
    amounts.extend(round(float(v.replace(',','').replace('，','')),2) for v in candidates)
  values=sorted(set(amounts))
  if values:
   if len(values)==1:fields['amount']=values[0]
   else:warnings.append('金额存在多个候选值，请对照原件确认')
   break
 for line in lines:
  merchant=re.search(r'(?:销售方名称|销售方|供应商|商户|商家|收款单位|SELLER|MERCHANT)\s*[:：]?\s*(.+)',line,re.I)
  if merchant and len(merchant.group(1).strip())>=2:fields['merchant']=merchant.group(1).strip()[:100];break
 invoice=re.search(r'(?:发票号码|发票号|票据号码|INVOICE\s*(?:NO|NUMBER))\s*[:：#.]?\s*([A-Za-z0-9-]{6,30})',clean,re.I)
 if invoice:fields['invoice_number']=invoice.group(1)
 if any(k in clean for k in ['采购','进货','蔬菜','原材料','入库']):fields['document_class']='purchase'
 elif any(k in clean for k in ['固定资产','电脑','设备购置']):fields['document_class']='asset'
 elif any(k in clean for k in ['银行回单','付款凭证','转账凭证']):fields['document_class']='payment'
 elif any(k in clean for k in ['报销','维修','洗涤','服务费']):fields['document_class']='expense'
 for terms,category in [(['维修'],'repair'),(['洗涤'],'laundry'),(['食材','蔬菜'],'food'),(['水电','电费','水费'],'utilities'),(['客用品','洗护','清洁用品'],'supplies')]:
  if any(t in clean for t in terms):fields['category']=category;break
 if fields['amount'] is None:warnings.append('未确认含税总额，需要财务补充')
 if fields['day'] is None:warnings.append('未确认单据归属日期，需要财务补充')
 warnings.append('识别仅为建议；采购入库、预付款、资产和实际耗用费用必须区分')
 return {'fields':fields,'warnings':warnings,'needs_confirmation':True,'engine':'local_ocr','text':clean[:24000]}

def analyze(files,data):
 text='\n'.join(document_text(path,mime,data) for path,mime in files)
 if not text.strip():raise ValueError('未识别到文字，文件已归档，请补拍或人工核对')
 return suggest(text)
