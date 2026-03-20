#!/usr/bin/env python3
"""
Construtor de Descritivo Funcional — Servidor de Geração de Descritivo
Uso: python guardian_server.py  (ou duplo clique em iniciar_servidor.bat)
Requer: python-docx  (pip install python-docx)
"""
import http.server, json, os, sys, re, shutil, io, tempfile, zipfile, datetime, uuid, subprocess
from pathlib import Path

# ── PostgreSQL (instala se necessário) ────────────────────────
def _get_db():
    """Retorna conexão PostgreSQL usando DATABASE_URL do ambiente."""
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(db_url, sslmode='disable', connect_timeout=5)
        return conn
    except ImportError:
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'psycopg2-binary',
                     '--break-system-packages', '-q'], check=True)
            import psycopg2
            conn = psycopg2.connect(db_url, sslmode='disable', connect_timeout=5)
            return conn
        except Exception as e:
            print(f'  [DB] psycopg2 indisponível: {e}')
            return None
    except Exception as e:
        print(f'  [DB] Conexão falhou: {e}')
        return None

def _init_db():
    """Cria tabela projetos se não existir."""
    conn = _get_db()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS projetos (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                analista    VARCHAR(120),
                cliente     VARCHAR(200),
                cidade      VARCHAR(120),
                revisao     VARCHAR(20),
                doc_date    VARCHAR(20),
                ct_hardware VARCHAR(80),
                ct_cloud    VARCHAR(80),
                filial      VARCHAR(120),
                status      VARCHAR(20) DEFAULT 'ativo',
                criado_em   TIMESTAMP DEFAULT NOW(),
                payload     JSONB NOT NULL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_proj_analista ON projetos(analista)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_proj_cliente  ON projetos(cliente)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_proj_status   ON projetos(status)")
        conn.commit()
        cur.close()
        conn.close()
        print('  [DB] Tabela projetos OK')
    except Exception as e:
        print(f'  [DB] Init falhou: {e}')
        try: conn.close()
        except: pass

def _salvar_projeto(data: dict) -> str | None:
    """Salva projeto no PostgreSQL. Retorna o ID gerado ou None se falhar."""
    conn = _get_db()
    if not conn: return None
    try:
        # Remover base64 grandes do payload para não inflar o banco
        payload = {k: v for k, v in data.items()
                   if k not in ('clientLogoB64', 'clientImgB64', 'htmlContent')}
        payload['htmlContent_preview'] = (data.get('htmlContent') or '')[:500]
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO projetos
                (analista, cliente, cidade, revisao, doc_date,
                 ct_hardware, ct_cloud, filial, payload)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            data.get('analystName',''),
            data.get('clientName',''),
            data.get('clientCity',''),
            data.get('docRevision','Rev00'),
            data.get('docDate',''),
            data.get('ctHardware',''),
            data.get('ctCloud',''),
            data.get('clientFilial',''),
            json.dumps(payload)
        ))
        proj_id = str(cur.fetchone()[0])
        conn.commit()
        cur.close()
        conn.close()
        print(f'  [DB] Projeto salvo: {proj_id[:8]}...')
        return proj_id
    except Exception as e:
        print(f'  [DB] Salvar falhou: {e}')
        try: conn.close()
        except: pass
        return None

def _listar_projetos(analista='', busca='', limite=50) -> list:
    """Lista projetos ativos com filtros opcionais."""
    conn = _get_db()
    if not conn: return []
    try:
        cur = conn.cursor()
        conds = ["status = 'ativo'"]
        params = []
        if analista:
            conds.append('analista ILIKE %s')
            params.append(f'%{analista}%')
        if busca:
            conds.append('(cliente ILIKE %s OR cidade ILIKE %s OR ct_hardware ILIKE %s)')
            params += [f'%{busca}%', f'%{busca}%', f'%{busca}%']
        where = ' AND '.join(conds)
        cur.execute(f"""
            SELECT id, analista, cliente, cidade, revisao, doc_date,
                   ct_hardware, ct_cloud, filial, criado_em
            FROM projetos
            WHERE {where}
            ORDER BY criado_em DESC
            LIMIT %s
        """, params + [limite])
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{'id': str(r[0]), 'analista': r[1], 'cliente': r[2],
                 'cidade': r[3], 'revisao': r[4], 'doc_date': r[5],
                 'ct_hardware': r[6], 'ct_cloud': r[7], 'filial': r[8],
                 'criado_em': r[9].strftime('%d/%m/%Y %H:%M') if r[9] else ''}
                for r in rows]
    except Exception as e:
        print(f'  [DB] Listar falhou: {e}')
        try: conn.close()
        except: pass
        return []

def _carregar_projeto(proj_id: str) -> dict | None:
    """Retorna payload completo de um projeto para clonar."""
    conn = _get_db()
    if not conn: return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT payload FROM projetos WHERE id = %s AND status = 'ativo'",
                    (proj_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f'  [DB] Carregar falhou: {e}')
        try: conn.close()
        except: pass
        return None

def _excluir_projeto(proj_id: str) -> bool:
    """Soft-delete: marca status = 'excluido'."""
    conn = _get_db()
    if not conn: return False
    try:
        cur = conn.cursor()
        cur.execute("UPDATE projetos SET status='excluido' WHERE id=%s", (proj_id,))
        ok = cur.rowcount > 0
        conn.commit()
        cur.close()
        conn.close()
        return ok
    except Exception as e:
        print(f'  [DB] Excluir falhou: {e}')
        try: conn.close()
        except: pass
        return False

# Instalar python-docx se necessário
try:
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
except ImportError:
    print("Instalando python-docx...")
    import subprocess
    subprocess.run([sys.executable,'-m','pip','install','python-docx',
                    '--break-system-packages','-q'])
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

BUILDER_HTML = Path(__file__).parent / 'builder-descritivo.html'
PORT = int(os.environ.get('PORT', 5555))
HERE = Path(__file__).parent


# ══════════ GERADOR DOCX PURO (python-docx, sem LibreOffice) ══════════
"""
build_docx_pure — Gerador python-docx puro do Descritivo Funcional Guardian PRO
Sem LibreOffice. Especificações baseadas nos modelos Toledo de referência.
"""
try:
    import io, base64, re
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor, Emu
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    _DOCX_AVAILABLE = True
except ImportError as _docx_err:
    print(f'  [AVISO] python-docx indisponível: {_docx_err}')
    _DOCX_AVAILABLE = False

# ── Cores Toledo ──────────────────────────────────────────────────────────────
if _DOCX_AVAILABLE:
    C_AZUL_ESCURO = RGBColor(0x1A,0x3A,0x6B)
    C_AZUL_MED    = RGBColor(0x2E,0x75,0xB6)
    C_AZUL_HDR    = RGBColor(0x44,0x72,0xC4)
    C_BRANCO      = RGBColor(0xFF,0xFF,0xFF)

# ── Medidas de página (DXA) — baseadas no modelo Toledo de referência ─────────
# Margens: top/bot=2.54cm=1440DXA, left/right=1.91cm=1080DXA
PG_W      = 12242; PG_H    = 15842
MG_TOP    = 1440;  MG_BOT  = 1440
MG_LEFT   = 1080;  MG_RIGHT = 1080
MG_HEADER = 567;   MG_FOOTER = 567
CONTENT_W = PG_W - MG_LEFT - MG_RIGHT  # 10082 DXA ≈ 17.8cm

def cm2emu(c): return int(c * 360000)
def dxa2emu(d): return int(d * 914.4)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _spacing(para, before=0, after=0):
    pPr = para._p.get_or_add_pPr()
    for s in pPr.findall(qn('w:spacing')): pPr.remove(s)
    sp = OxmlElement('w:spacing')
    sp.set(qn('w:before'), str(before))
    sp.set(qn('w:after'),  str(after))
    pPr.append(sp)

def _cell_shading(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    for s in tcPr.findall(qn('w:shd')): tcPr.remove(s)
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'),'clear'); shd.set(qn('w:color'),'auto')
    shd.set(qn('w:fill'), fill)
    tcPr.append(shd)

def _cell_borders(cell, color='C0C8D8', sz=4):
    tcPr = cell._tc.get_or_add_tcPr()
    for b in tcPr.findall(qn('w:tcBorders')): tcPr.remove(b)
    brd = OxmlElement('w:tcBorders')
    for side in ['top','left','bottom','right']:
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'),'single'); el.set(qn('w:sz'),str(sz))
        el.set(qn('w:space'),'0');    el.set(qn('w:color'),color)
        brd.append(el)
    # tcBorders deve vir ANTES de shd no CT_TcPr
    shd = tcPr.find(qn('w:shd'))
    if shd is not None: shd.addprevious(brd)
    else: tcPr.append(brd)

def _cell_width(cell, w_dxa):
    tcPr = cell._tc.get_or_add_tcPr()
    for t in tcPr.findall(qn('w:tcW')): tcPr.remove(t)
    tcW = OxmlElement('w:tcW')
    tcW.set(qn('w:w'), str(w_dxa)); tcW.set(qn('w:type'),'dxa')
    tcPr.insert(0, tcW)

def _cell_margin(cell, val=120):
    tcPr = cell._tc.get_or_add_tcPr()
    for m in tcPr.findall(qn('w:tcMar')): tcPr.remove(m)
    tcMar = OxmlElement('w:tcMar')
    for side in ['top','left','bottom','right']:
        m = OxmlElement(f'w:{side}')
        m.set(qn('w:w'), str(val)); m.set(qn('w:type'),'dxa')
        tcMar.append(m)
    tcPr.append(tcMar)

def _no_borders_tbl(tbl):
    tblPr = tbl._tbl.find(qn('w:tblPr'))
    if tblPr is None: tblPr = OxmlElement('w:tblPr'); tbl._tbl.insert(0, tblPr)
    for b in tblPr.findall(qn('w:tblBorders')): tblPr.remove(b)
    brd = OxmlElement('w:tblBorders')
    for s in ['top','left','bottom','right','insideH','insideV']:
        el = OxmlElement(f'w:{s}'); el.set(qn('w:val'),'none')
        brd.append(el)
    # tblBorders deve vir após tblW
    tblW = tblPr.find(qn('w:tblW'))
    if tblW is not None: tblW.addnext(brd)
    else: tblPr.append(brd)

def _tbl_width(tbl, w_dxa):
    # Define largura via atributo tblLayout=fixed para que o Word respeite as tcW
    tblPr = tbl._tbl.find(qn('w:tblPr'))
    if tblPr is None: tblPr = OxmlElement('w:tblPr'); tbl._tbl.insert(0, tblPr)
    # Remover tblW existente (evita erro de schema)
    for t in tblPr.findall(qn('w:tblW')): tblPr.remove(t)
    # Usar tblLayout fixed para respeitar widths das células
    for t in tblPr.findall(qn('w:tblLayout')): tblPr.remove(t)
    tblLayout = OxmlElement('w:tblLayout')
    tblLayout.set(qn('w:type'), 'fixed')
    tblPr.append(tblLayout)

def _add_h1_shading(para):
    pPr = para._p.get_or_add_pPr()
    for s in pPr.findall(qn('w:shd')): pPr.remove(s)
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'),'clear'); shd.set(qn('w:color'),'auto')
    shd.set(qn('w:fill'),'1A3A6B')
    # Ordem schema CT_PPr: pStyle > pBdr > shd > spacing > ind > jc
    # Inserir shd antes de spacing, ind ou jc (o que vier primeiro)
    ref = None
    for candidate in ['w:spacing','w:ind','w:jc','w:rPr']:
        ref = pPr.find(qn(candidate))
        if ref is not None: break
    if ref is not None: ref.addprevious(shd)
    else: pPr.append(shd)

def _add_h2_border(para):
    pPr = para._p.get_or_add_pPr()
    for b in pPr.findall(qn('w:pBdr')): pPr.remove(b)
    pBdr = OxmlElement('w:pBdr')
    bot  = OxmlElement('w:bottom')
    bot.set(qn('w:val'),'single'); bot.set(qn('w:sz'),'6')
    bot.set(qn('w:space'),'1');   bot.set(qn('w:color'),'2E75B6')
    pBdr.append(bot)
    # pBdr vem depois de pStyle/numPr mas antes de shd/spacing/ind
    ref = None
    for candidate in ['w:shd','w:spacing','w:ind','w:jc','w:rPr']:
        ref = pPr.find(qn(candidate))
        if ref is not None: break
    if ref is not None: ref.addprevious(pBdr)
    else: pPr.append(pBdr)

def _add_hyperlink(para, text, url):
    r_id = para.part.relate_to(url,
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink',
        is_external=True)
    hl = OxmlElement('w:hyperlink'); hl.set(qn('r:id'), r_id)
    r  = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    rSt = OxmlElement('w:rStyle'); rSt.set(qn('w:val'),'Hyperlink')
    rPr.append(rSt); r.append(rPr)
    t = OxmlElement('w:t'); t.text = text; r.append(t)
    hl.append(r); para._p.append(hl)

def _add_toc(doc):
    p = doc.add_paragraph(); _spacing(p, before=0, after=80)
    run = p.add_run()
    for ftype, text in [('begin',None),('separate',None)]:
        fc = OxmlElement('w:fldChar'); fc.set(qn('w:fldCharType'), ftype)
        run._r.append(fc)
        if ftype == 'begin':
            instr = OxmlElement('w:instrText')
            instr.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
            instr.text = ' TOC \\o "1-2" \\h \\z \\u '
            run._r.append(instr)
    hint = p.add_run('Clique com botão direito → "Atualizar campo" para gerar o índice.')
    hint.font.size = Pt(10); hint.font.italic = True
    hint.font.color.rgb = C_AZUL_MED
    p2 = doc.add_paragraph(); _spacing(p2, before=0, after=0)
    run2 = p2.add_run()
    fc_end = OxmlElement('w:fldChar'); fc_end.set(qn('w:fldCharType'),'end')
    run2._r.append(fc_end)

def _add_footer(section, doc_title):
    """Rodapé Toledo: nome do doc à esq | Página X de Y à dir — 8pt, linha sep."""
    ftr = section.footer
    for p in list(ftr.paragraphs):
        p._element.getparent().remove(p._element)

    def _fld(para, instr, prefix='', suffix=''):
        if prefix:
            r = para.add_run(prefix)
            r.font.size = Pt(8); r.font.name = 'Arial'
        fc1 = OxmlElement('w:fldChar'); fc1.set(qn('w:fldCharType'),'begin')
        it  = OxmlElement('w:instrText')
        it.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
        it.text = ' ' + instr + ' '
        fc2 = OxmlElement('w:fldChar'); fc2.set(qn('w:fldCharType'),'separate')
        fc3 = OxmlElement('w:fldChar'); fc3.set(qn('w:fldCharType'),'end')
        run = para.add_run()
        run._r.append(fc1); run._r.append(it); run._r.append(fc2); run._r.append(fc3)
        run.font.size = Pt(8); run.font.name = 'Arial'
        if suffix:
            r2 = para.add_run(suffix)
            r2.font.size = Pt(8); r2.font.name = 'Arial'

    # Parágrafo único com tab stop central/direita
    p = ftr.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    # Tab stop à direita — DEVE vir antes de spacing no CT_PPr
    tabs = OxmlElement('w:tabs')
    tab  = OxmlElement('w:tab')
    tab.set(qn('w:val'),  'right')
    tab.set(qn('w:pos'),  str(CONTENT_W))
    tabs.append(tab)
    pPr.append(tabs)
    # Spacing DEPOIS de tabs (ordem CT_PPr: tabs > spacing)
    _spacing(p, before=0, after=0)
    # Linha separadora acima do rodapé
    pBdr = OxmlElement('w:pBdr')
    top  = OxmlElement('w:top')
    top.set(qn('w:val'),   'single'); top.set(qn('w:sz'),  '6')
    top.set(qn('w:space'), '1');      top.set(qn('w:color'),'C0C8D8')
    pBdr.append(top); pPr.insert(0, pBdr)

    # Lado esquerdo: nome do documento
    r_left = p.add_run(doc_title[:60] if doc_title else 'Guardian PRO — Descritivo Funcional')
    r_left.font.size = Pt(8); r_left.font.name = 'Arial'
    r_left.font.color.rgb = RGBColor(0x66,0x66,0x66)

    # Tab para direita
    r_tab = p.add_run(); r_tab._r.append(OxmlElement('w:tab'))

    # Lado direito: Página X de Y
    _fld(p, 'PAGE', prefix='Página ')
    _fld(p, 'NUMPAGES', prefix=' de ')

def _page_break(doc):
    p = doc.add_paragraph(); _spacing(p, before=0, after=0)
    r = p.add_run()
    br = OxmlElement('w:br'); br.set(qn('w:type'),'page')
    r._r.append(br)

def _sep_line(container, color='1A3A6B', sz=6):
    p = container.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    # pBdr DEVE vir antes de spacing no CT_PPr
    pBdr = OxmlElement('w:pBdr')
    bot  = OxmlElement('w:bottom')
    bot.set(qn('w:val'),'single'); bot.set(qn('w:sz'),str(sz))
    bot.set(qn('w:space'),'1');   bot.set(qn('w:color'),color)
    pBdr.append(bot); pPr.append(pBdr)
    # Adicionar spacing depois de pBdr
    _spacing(p, before=60, after=0)

# ── Parser HTML → python-docx ─────────────────────────────────────────────────
def _html_to_docx(doc, html):
    from html.parser import HTMLParser

    class Builder(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack   = []          # (tag, attrs)
            self.para    = None
            self.in_tbl  = False
            self.tbl_rows = []
            self.cur_row  = []
            self.cur_cell = ''
            self.list_lvl = 0
            self.is_ol    = False
            self.ol_n     = 0

        def _tags(self): return [t for t,_ in self.stack]

        def handle_starttag(self, tag, attrs):
            ad = dict(attrs); self.stack.append((tag, ad))
            if tag == 'h1':
                self.para = doc.add_paragraph(style='Heading 1')
                _spacing(self.para, before=120, after=60)
                self.para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            elif tag == 'h2':
                self.para = doc.add_paragraph(style='Heading 2')
                _spacing(self.para, before=100, after=40)
                self.para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            elif tag == 'h3':
                self.para = doc.add_paragraph(style='Heading 3')
                _spacing(self.para, before=80, after=30)
            elif tag == 'p':
                self.para = doc.add_paragraph()
                _spacing(self.para, before=60, after=60)
                self.para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            elif tag in ('ul','ol'):
                self.list_lvl += 1
                self.is_ol = (tag == 'ol')
                if self.is_ol: self.ol_n = 0
            elif tag == 'li':
                self.para = doc.add_paragraph(); _spacing(self.para,30,30)
                pPr = self.para._p.get_or_add_pPr()
                ind = OxmlElement('w:ind')
                ind.set(qn('w:left'),    str(720*self.list_lvl))
                ind.set(qn('w:hanging'), '360')
                pPr.append(ind)
                br = self.para.add_run()
                if self.is_ol:
                    self.ol_n += 1; br.text = f'{self.ol_n}.\u00a0'
                else:
                    br.text = '\u2022\u00a0'
                br.font.size = Pt(11)
            elif tag == 'table':
                self.in_tbl = True; self.tbl_rows = []
            elif tag == 'tr':
                self.cur_row = []
            elif tag in ('td','th'):
                self.cur_cell = ''
            elif tag == 'br' and self.para:
                self.para.add_run('\n')

        def handle_endtag(self, tag):
            if self.stack and self.stack[-1][0] == tag: self.stack.pop()
            if tag in ('h1','h2','h3','p','li'): self.para = None
            elif tag in ('ul','ol'):
                self.list_lvl = max(0, self.list_lvl-1)
            elif tag in ('td','th'):
                self.cur_row.append(self.cur_cell.strip())
            elif tag == 'tr':
                if self.cur_row: self.tbl_rows.append(self.cur_row)
            elif tag == 'table':
                self.in_tbl = False
                if not self.tbl_rows: return
                nc = max(len(r) for r in self.tbl_rows)
                nr = len(self.tbl_rows)
                cw = CONTENT_W // nc
                tbl = doc.add_table(rows=nr, cols=nc)
                tbl.style = 'Table Grid'
                _tbl_width(tbl, CONTENT_W)
                for ri, row in enumerate(self.tbl_rows):
                    is_h = (ri == 0)
                    for ci, txt in enumerate(row):
                        if ci >= nc: break
                        cell = tbl.rows[ri].cells[ci]
                        fill = ('4472C4' if is_h else
                                ('F2F2F2' if ri%2==0 else 'FFFFFF'))
                        _cell_shading(cell, fill)
                        _cell_borders(cell)
                        _cell_width(cell, cw)
                        _cell_margin(cell)
                        cp = cell.paragraphs[0]
                        _spacing(cp, 60, 60)
                        run = cp.add_run(txt)
                        run.font.name = 'Arial'; run.font.size = Pt(10)
                        if is_h:
                            run.font.bold = True
                            run.font.color.rgb = C_BRANCO
                self.para = None

        def handle_data(self, data):
            tags = self._tags()
            if self.in_tbl and ('td' in tags or 'th' in tags):
                self.cur_cell += data; return
            if not self.para or not data.strip(): return
            b = 'b' in tags or 'strong' in tags
            i = 'i' in tags or 'em' in tags
            h1 = 'h1' in tags; h2 = 'h2' in tags; h3 = 'h3' in tags
            run = self.para.add_run(data)
            if h1:
                run.font.name='Arial Black'; run.font.size=Pt(13)
                run.font.bold=True; run.font.color.rgb=C_BRANCO
            elif h2:
                run.font.name='Arial Black'; run.font.size=Pt(12)
                run.font.color.rgb=C_AZUL_MED
            elif h3:
                run.font.name='Arial'; run.font.size=Pt(11)
                run.font.bold=True; run.font.color.rgb=C_AZUL_ESCURO
            else:
                run.font.name='Arial'; run.font.size=Pt(11)
                run.font.bold=b; run.font.italic=i

    Builder().feed(html)

    # Aplicar shading/border especial nos headings gerados
    for p in doc.paragraphs:
        sn = (p.style.name or '') if p.style else ''
        if 'Heading 1' in sn: _add_h1_shading(p)
        elif 'Heading 2' in sn: _add_h2_border(p)


# ── Função principal ──────────────────────────────────────────────────────────
def build_docx_pure(data: dict, toledo_logo: bytes, guardian_banner: bytes) -> bytes:
    doc = Document()

    # Página A4
    sec = doc.sections[0]
    sec.page_width    = Emu(dxa2emu(PG_W))
    sec.page_height   = Emu(dxa2emu(PG_H))
    sec.top_margin      = Emu(dxa2emu(MG_TOP))
    sec.bottom_margin   = Emu(dxa2emu(MG_BOT))
    sec.left_margin     = Emu(dxa2emu(MG_LEFT))
    sec.right_margin    = Emu(dxa2emu(MG_RIGHT))
    sec.header_distance = Emu(dxa2emu(MG_HEADER))
    sec.footer_distance = Emu(dxa2emu(MG_FOOTER))
    # Ativar cabeçalho/rodapé diferentes na 1a página
    # Nota: titlePg removido — rodapé aparece em todas as páginas (incluindo capa)

    # Estilos
    doc.styles['Normal'].font.name = 'Arial'
    doc.styles['Normal'].font.size = Pt(11)
    def _set_outline_lvl(style_elem, lvl):
        pPr = style_elem.get_or_add_pPr()
        for o in pPr.findall(qn('w:outlineLvl')): pPr.remove(o)
        ol = OxmlElement('w:outlineLvl')
        ol.set(qn('w:val'), str(lvl))
        pPr.append(ol)

    for h,nm,sz,rgb,lvl in [
        ('Heading 1','Arial Black',13,C_BRANCO,0),
        ('Heading 2','Arial Black',12,C_AZUL_MED,1),
    ]:
        s = doc.styles[h]
        s.font.name=nm; s.font.size=Pt(sz)
        s.font.color.rgb=rgb; s.font.bold=True
        _set_outline_lvl(s._element, lvl)
    try:
        h3s = doc.styles['Heading 3']
    except:
        h3s = doc.styles.add_style('Heading 3',1)
    h3s.font.name='Arial'; h3s.font.size=Pt(11); h3s.font.bold=True
    h3s.font.color.rgb=C_AZUL_ESCURO
    _set_outline_lvl(h3s._element, 2)

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    hdr = sec.header
    for p in list(hdr.paragraphs): p._element.getparent().remove(p._element)

    htbl = hdr.add_table(rows=1, cols=2, width=Emu(dxa2emu(CONTENT_W)))
    _no_borders_tbl(htbl)
    # Definir largura via layout fixed (sem tblW para evitar erro de schema)
    _tbl_width(htbl, CONTENT_W)
    hw = CONTENT_W // 2
    cl = htbl.rows[0].cells[0]; cr = htbl.rows[0].cells[1]
    for c in [cl, cr]: _cell_width(c, hw)

    pl = cl.paragraphs[0]
    pl.alignment = WD_ALIGN_PARAGRAPH.LEFT
    client_logo_b64 = data.get('clientLogoB64','')
    if client_logo_b64:
        try:
            b64data = client_logo_b64.split('base64,',1)[-1]
            cimg = base64.b64decode(b64data)
            pl.add_run().add_picture(io.BytesIO(cimg), width=Cm(3.0))
        except:
            r=pl.add_run('(logo do cliente)'); r.font.size=Pt(9)
            r.font.italic=True; r.font.color.rgb=RGBColor(0xAA,0xAA,0xAA)
    else:
        r=pl.add_run('(logo do cliente)'); r.font.size=Pt(9)
        r.font.italic=True; r.font.color.rgb=RGBColor(0xAA,0xAA,0xAA)

    pr = cr.paragraphs[0]
    pr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    if toledo_logo:
        pr.add_run().add_picture(io.BytesIO(toledo_logo),
                                  width=Cm(4.86), height=Cm(2.04))

    # Linha separadora no header (sem spacing para evitar erro de schema)
    p_sep = hdr.add_paragraph()
    pPr_s = p_sep._p.get_or_add_pPr()
    pBdr_s = OxmlElement('w:pBdr')
    bot_s  = OxmlElement('w:bottom')
    bot_s.set(qn('w:val'),'single'); bot_s.set(qn('w:sz'),'6')
    bot_s.set(qn('w:space'),'1');   bot_s.set(qn('w:color'),'1A3A6B')
    pBdr_s.append(bot_s)
    first_s = list(pPr_s)[0] if list(pPr_s) else None
    if first_s is not None: first_s.addprevious(pBdr_s)
    else: pPr_s.append(pBdr_s)

    # ── CAPA ──────────────────────────────────────────────────────────────────
    # Banner
    if guardian_banner:
        p = doc.add_paragraph(); _spacing(p, 0, 120)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(io.BytesIO(guardian_banner),
                                 width=Cm(18.43), height=Cm(7.72))

    # Título
    p = doc.add_paragraph(); _spacing(p, 120, 40)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run('DESCRITIVO FUNCIONAL')
    r.font.name='Cambria'; r.font.size=Pt(20)
    r.font.bold=True; r.font.color.rgb=C_AZUL_ESCURO

    # Subtítulo
    p = doc.add_paragraph(); _spacing(p, 0, 100)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run('GUARDIAN PRO \u2014 Software para Gerenciamento de Operações de Pesagem')
    r.font.name='Cambria'; r.font.size=Pt(13)
    r.font.color.rgb=RGBColor(0x22,0x22,0x22)

    # Nome cliente
    cn = (data.get('clientName') or '').upper()
    cc = (data.get('clientCity') or '').upper()
    if cn:
        p = doc.add_paragraph(); _spacing(p, 60, 20)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(cn + (' \u2014 ' + cc if cc else ''))
        r.font.name='Cambria'; r.font.size=Pt(16)
        r.font.bold=True; r.font.color.rgb=C_AZUL_ESCURO

    cu = data.get('clientUnit','')
    if cu:
        p = doc.add_paragraph(); _spacing(p, 0, 80)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(cu); r.font.name='Cambria'; r.font.size=Pt(13)
        r.font.color.rgb=RGBColor(0x44,0x44,0x44)

    # Foto da unidade
    cib64 = data.get('clientImgB64','')
    if cib64:
        try:
            cimg = base64.b64decode(cib64.split('base64,',1)[-1])
            p = doc.add_paragraph(); _spacing(p, 40, 40)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(io.BytesIO(cimg), width=Cm(14))
        except: pass

    # Tabela identificação
    fields = [
        ('CT / OV Hardware e Serviços', data.get('ctHardware','')),
        ('Licenciamento Cloud',         data.get('ctCloud','')),
        ('Filial(is)',                  data.get('clientFilial','')),
        ('Analista Responsável',        data.get('analystName','')),
        ('Revisão',                     data.get('docRevision','')),
        ('Data do Documento',           data.get('docDate','')),
    ]
    rows = [(l,v) for l,v in fields if v]
    if rows:
        doc.add_paragraph()._p  # espaçador
        CL, CV = 3600, 4800
        tbl = doc.add_table(rows=len(rows), cols=2)
        tbl.style = 'Table Grid'
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        _tbl_width(tbl, CL+CV)
        for ri, (lbl, val) in enumerate(rows):
            for cell, w, txt, bold in [
                (tbl.rows[ri].cells[0], CL, lbl, True),
                (tbl.rows[ri].cells[1], CV, val, False),
            ]:
                _cell_shading(cell, 'EDF0F7' if bold else
                              ('FFFFFF' if ri%2==0 else 'F4F6FB'))
                _cell_borders(cell); _cell_width(cell, w); _cell_margin(cell)
                cp = cell.paragraphs[0]; _spacing(cp, 80, 80)
                run = cp.add_run(txt)
                run.font.name='Cambria'; run.font.size=Pt(11); run.font.bold=bold

    # URL
    p = doc.add_paragraph(); _spacing(p, 80, 60)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_hyperlink(p, 'www.toledobrasil.com/produto/guardian',
                   'http://www.toledobrasil.com/produto/guardian')

    _sep_line(doc, '1A3A6B', 8)
    _page_break(doc)

    # ── ÍNDICE ────────────────────────────────────────────────────────────────
    p = doc.add_paragraph(); _spacing(p, 0, 80)
    r = p.add_run('Índice')
    r.font.name='Arial Black'; r.font.size=Pt(14)
    r.font.bold=True; r.font.color.rgb=C_AZUL_ESCURO
    _add_toc(doc)
    _page_break(doc)

    # ── CONTEÚDO ──────────────────────────────────────────────────────────────
    html = data.get('htmlContent','')
    if html:
        _html_to_docx(doc, html)

    # Rodapé Toledo: nome do doc à esq | Página X de Y à dir
    doc_title = f"Descritivo Funcional_GuardianPRO_{data.get('clientName','')}_"                 f"{data.get('docRevision','Rev00')}"
    _add_footer(sec, doc_title)

    buf = io.BytesIO()
    doc.save(buf)
    # Pós-processamento: corrigir settings.xml e reordenar XML
    import zipfile as _zf, re as _re
    from lxml import etree as _et
    _W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

    def _fix_tbl_order(xml_bytes):
        """Reordena tblPr para garantir tblStyle > jc > tblW > tblBorders > tblLook"""
        root = _et.fromstring(xml_bytes)
        tbl_order = ['tblStyle','tblpPr','jc','tblW','tblBorders',
                     'tblCellSpacing','tblInd','tblCellMar','tblLayout','tblLook']
        for tblPr in root.iter(f'{{{_W}}}tblPr'):
            children = list(tblPr)
            if not children: continue
            # Reordenar conforme tbl_order
            ordered, rest = [], []
            for key in tbl_order:
                for c in children:
                    if c.tag == f'{{{_W}}}{key}':
                        ordered.append(c); break
            rest = [c for c in children if c not in ordered]
            for c in children: tblPr.remove(c)
            for c in ordered + rest: tblPr.append(c)
        return _et.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)

    buf_in = io.BytesIO(buf.getvalue()); buf_out = io.BytesIO()
    with _zf.ZipFile(buf_in,'r') as zi, _zf.ZipFile(buf_out,'w',_zf.ZIP_DEFLATED) as zo:
        for item in zi.infolist():
            data = zi.read(item.filename)
            if item.filename == 'word/settings.xml':
                xml = data.decode('utf-8')
                xml = _re.sub(r'<w:zoom([^>]*)/>', 
                    lambda m: f'<w:zoom{m.group(1)} w:percent="100"/>'
                    if 'percent' not in m.group(1) else m.group(0), xml)
                data = xml.encode('utf-8')
            elif item.filename in ('word/document.xml','word/header1.xml'):
                try: data = _fix_tbl_order(data)
                except: pass
            zo.writestr(item, data)
    return buf_out.getvalue()

# ══════════════════════════════════════════════════════════════════════

# ── Caminhos das imagens (embutidas no guardian_server.py) ────
# As imagens serão extraídas do builder-descritivo.html
import base64, struct

def extract_imgs_from_builder():
    """Extrai as imagens base64 do builder HTML"""
    imgs = {}
    try:
        html = BUILDER_HTML.read_text(encoding='utf-8')
        for key in ['guardian_capa','logo_toledo_real']:
            m = re.search(rf"{key}:\s*'(data:image/[^']+)'", html)
            if m:
                b64 = m.group(1).split(',',1)[1]
                imgs[key] = base64.b64decode(b64)
    except Exception as e:
        print(f"  [AVISO] Não foi possível extrair imagens: {e}")
    return imgs

# ── Cores Toledo ──────────────────────────────────────────────
C_AZUL     = RGBColor(0x1A,0x3A,0x6B)
C_AZUL_MED = RGBColor(0x2E,0x75,0xB6)
C_AZUL_CLR = RGBColor(0x44,0x72,0xC4)
C_BRANCO   = RGBColor(0xFF,0xFF,0xFF)

# ── Helpers ───────────────────────────────────────────────────
def set_cell_bg(cell, hex_color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for s in tcPr.findall(qn('w:shd')): tcPr.remove(s)
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'),'clear'); shd.set(qn('w:color'),'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)

def remove_table_borders(tbl_el):
    tblPr = tbl_el.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr'); tbl_el.insert(0,tblPr)
    for b in tblPr.findall(qn('w:tblBorders')): tblPr.remove(b)
    tblBrd = OxmlElement('w:tblBorders')
    for side in ['top','left','bottom','right','insideH','insideV']:
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'),'none'); el.set(qn('w:sz'),'0')
        el.set(qn('w:space'),'0'); el.set(qn('w:color'),'auto')
        tblBrd.append(el)
    tblPr.append(tblBrd)

def set_para_shd(para, hex_color):
    """shd deve vir antes de spacing/jc no pPr"""
    pPr = para._p.get_or_add_pPr()
    for s in pPr.findall(qn('w:shd')): pPr.remove(s)
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'),'clear'); shd.set(qn('w:color'),'auto')
    shd.set(qn('w:fill'), hex_color)
    # Inserir antes de spacing ou jc para manter ordem do schema
    for anchor_tag in [qn('w:spacing'), qn('w:jc'), qn('w:rPr')]:
        anchor = pPr.find(anchor_tag)
        if anchor is not None:
            anchor.addprevious(shd); return
    pPr.append(shd)

def add_h1(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after  = Pt(5)
    set_para_shd(p, '1A3A6B')
    r = p.add_run(text)
    r.font.name='Arial Black'; r.font.size=Pt(13)
    r.font.bold=True; r.font.color.rgb=C_BRANCO

def add_h2(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after  = Pt(4)
    r = p.add_run(text)
    r.font.name='Arial Black'; r.font.size=Pt(12)
    r.font.color.rgb=C_AZUL_MED
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bot = OxmlElement('w:bottom')
    bot.set(qn('w:val'),'single'); bot.set(qn('w:sz'),'4')
    bot.set(qn('w:space'),'1'); bot.set(qn('w:color'),'2E75B6')
    pBdr.append(bot); pPr.append(pBdr)

def add_h3(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after  = Pt(3)
    r = p.add_run(text)
    r.font.name='Arial'; r.font.size=Pt(11)
    r.font.bold=True; r.font.color.rgb=C_AZUL_MED

def add_body(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after  = Pt(2)
    r = p.add_run(text)
    r.font.name='Arial'; r.font.size=Pt(11)

def add_bullet(doc, text):
    p = doc.add_paragraph(style='List Bullet')
    r = p.add_run(text)
    r.font.name='Arial'; r.font.size=Pt(11)
    p.paragraph_format.left_indent = Cm(0.5)

def make_table(doc, headers, rows, col_widths_cm):
    tbl = doc.add_table(rows=1+len(rows), cols=len(headers))
    tbl.style = 'Table Grid'
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Cabeçalho
    hrow = tbl.rows[0]
    for i,(cell,h) in enumerate(zip(hrow.cells, headers)):
        cell.width = Cm(col_widths_cm[i])
        set_cell_bg(cell,'4472C4')
        p = cell.paragraphs[0]
        r = p.add_run(str(h))
        r.font.name='Arial'; r.font.size=Pt(10)
        r.font.bold=True; r.font.color.rgb=C_BRANCO
    # Dados
    for ri,row in enumerate(rows):
        tr = tbl.rows[ri+1]
        for ci,(cell,val) in enumerate(zip(tr.cells,row)):
            cell.width = Cm(col_widths_cm[ci] if ci<len(col_widths_cm) else 3)
            set_cell_bg(cell,'FFFFFF' if ri%2==0 else 'F2F2F2')
            p = cell.paragraphs[0]
            r = p.add_run(str(val or '—'))
            r.font.name='Arial'; r.font.size=Pt(10)

def strip_html(html):
    if not html: return ''
    h = re.sub(r'<b>(.*?)</b>',r'\1',html,flags=re.I)
    h = re.sub(r'<strong>(.*?)</strong>',r'\1',h,flags=re.I)
    h = re.sub(r'<[^>]+>','',h)
    h = h.replace('&lt;','<').replace('&gt;','>').replace('&amp;','&').replace('&nbsp;',' ')
    return re.sub(r'\s+',' ',h).strip()

def parse_html_content(doc, html):
    """Converte o HTML gerado pelo builder em parágrafos docx"""
    if not html: return
    # Remover CSS, scripts, capa
    html = re.sub(r'<style[\s\S]*?</style>','',html,flags=re.I)
    html = re.sub(r'<script[\s\S]*?</script>','',html,flags=re.I)
    html = re.sub(r'<img[^>]*>','',html,flags=re.I)
    # Pular a capa (até o primeiro H1 depois do page break)
    h1_match = re.search(r'<h1[^>]*>',html,re.I)
    if h1_match: html = html[h1_match.start():]

    for h1part in re.split(r'<h1[^>]*>',html,flags=re.I):
        h1m = re.match(r'(.*?)</h1>',h1part,re.I)
        if not h1m: continue
        add_h1(doc, strip_html(h1m.group(1)))
        rest = h1part[h1m.end():]
        for h2part in re.split(r'<h2[^>]*>',rest,flags=re.I):
            h2m = re.match(r'(.*?)</h2>',h2part,re.I)
            if h2m:
                add_h2(doc, strip_html(h2m.group(1)))
                _parse_block(doc, h2part[h2m.end():])
            else:
                _parse_block(doc, h2part)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

def _parse_block(doc, html):
    if not html or not html.strip(): return
    tables = re.findall(r'<table[\s\S]*?</table>',html,re.I)
    no_tbl = re.sub(r'<table[\s\S]*?</table>','\n§TBL§\n',html,flags=re.I)
    ti = 0
    for line in no_tbl.split('\n'):
        cl = line.strip()
        if not cl: continue
        if cl == '§TBL§':
            if ti < len(tables): _parse_table(doc, tables[ti]); ti+=1
        elif re.search(r'<h3',cl,re.I):
            t=strip_html(cl)
            if t: add_h3(doc,t)
        elif re.search(r'<li',cl,re.I):
            for item in re.findall(r'<li[^>]*>([\s\S]*?)</li>',cl,re.I) or [cl]:
                t=strip_html(item)
                if t: add_bullet(doc,t)
        else:
            t=strip_html(cl)
            if t and len(t)>2: add_body(doc,t)

def _parse_table(doc, html):
    hdr = re.search(r'<thead[\s\S]*?</thead>',html,re.I)
    headers = [strip_html(h) for h in re.findall(r'<th[^>]*>([\s\S]*?)</th>',
               hdr.group() if hdr else '',re.I)]
    tbody = re.search(r'<tbody[\s\S]*?</tbody>',html,re.I)
    rows = [[strip_html(td) for td in re.findall(r'<td[^>]*>([\s\S]*?)</td>',tr,re.I)]
            for tr in re.findall(r'<tr[^>]*>([\s\S]*?)</tr>',
            tbody.group() if tbody else html,re.I)
            if not re.search(r'<th',tr,re.I)]
    if not headers and not rows: return
    cols = max(len(headers), max((len(r) for r in rows),default=1))
    cw = round(15.27/cols, 2)
    col_widths = [cw]*cols
    make_table(doc, headers or rows[0], rows if headers else rows[1:], col_widths)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

# ── Cache de imagens (carregado uma vez ao iniciar) ───────────
_IMGS_CACHE = {}

def get_imgs():
    global _IMGS_CACHE
    if not _IMGS_CACHE:
        _IMGS_CACHE = extract_imgs_from_builder()
    return _IMGS_CACHE

def b64_src(key):
    """Retorna data URI base64 da imagem"""
    imgs = get_imgs()
    if key not in imgs: return ''
    import base64
    data = base64.b64encode(imgs[key]).decode()
    # Detectar tipo
    magic = imgs[key][:4]
    mime = 'image/png' if magic[:1] == b'\x89' else 'image/jpeg'
    return f"data:{mime};base64,{data}"

def build_html_doc(d):
    """Gera o HTML completo do descritivo — idêntico ao buildDoc() do browser"""
    guardian_src   = b64_src('guardian_capa')
    logo_src       = b64_src('logo_toledo_real')
    client_logo    = d.get('clientLogoB64','')
    client_img     = d.get('clientImgB64','')
    
    client_name = (d.get('clientName') or '').upper()
    client_city = (d.get('clientCity') or '').upper()
    client_unit = d.get('clientUnit','')
    
    # Tabela de identificação
    def row(label, value, even=False):
        bg = '#f4f6fb' if even else '#ffffff'
        return f'''<tr>
          <td style="padding:6pt 9pt;border:.5pt solid #c0c8d8;background:#edf0f7;font-weight:bold;width:150pt;font-family:Arial;font-size:10pt">{label}</td>
          <td style="padding:6pt 9pt;border:.5pt solid #c0c8d8;background:{bg};font-family:Arial;font-size:10pt">{value or 'A definir'}</td>
        </tr>'''

    id_rows = [
        row('CT / OV Hardware e Serviços', d.get('ctHardware'), False),
        row('Licenciamento Cloud', d.get('ctCloud'), True),
    ]
    if d.get('clientFilial'):
        id_rows.append(row('Filial(is)', d['clientFilial'], len(id_rows)%2==0))
    id_rows.append(row('Analista Responsável', d.get('analystName'), len(id_rows)%2==0))
    id_rows.append(row('Revisão', d.get('docRevision','Rev00'), len(id_rows)%2==0))
    id_rows.append(row('Data', d.get('docDate',''), len(id_rows)%2==0))

    # HTML do conteúdo (seções do descritivo)
    html_content = d.get('htmlContent','')

    # Variáveis auxiliares para evitar backslash em f-string (Python 3.11 compat)
    _banner_html = ("<img class='cov-banner' src='" + guardian_src + "' alt='Guardian PRO'>"
                    if guardian_src else "")
    _unit_html   = ("<div class='cov-unit'>" + client_unit + "</div>"
                    if client_unit else "")
    _cimg_html   = ("<img class='cov-client-img' src='" + client_img + "' alt='Unidade'>"
                    if client_img else "")

    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<style>
body{{font-family:Arial,sans-serif;font-size:11pt;color:#1a1a1a;line-height:1.65;margin:0}}
.pg{{max-width:960px;margin:0 auto;padding:40pt}}
h1{{font-family:"Arial Black",Arial;font-size:14pt;color:#fff;background:#1a3a6b;padding:8pt 10pt;margin:24pt 0 10pt;page-break-after:avoid}}
h2{{font-family:"Arial Black",Arial;font-size:12pt;color:#2e75b6;border-bottom:.5pt solid #2e75b6;padding-bottom:3pt;margin:16pt 0 7pt;page-break-after:avoid}}
h3{{font-family:Arial;font-size:11pt;font-weight:bold;color:#2c3e6b;margin:12pt 0 5pt}}
p{{margin:5pt 0;text-align:justify}}
ul,ol{{margin:6pt 0;padding-left:22pt}}
li{{margin-bottom:3pt}}
table{{width:100%;border-collapse:collapse;font-size:10pt;margin:10pt 0;page-break-inside:avoid}}
th{{background:#4472C4;color:#fff;padding:7pt 9pt;text-align:left;font-family:Arial;font-size:9.5pt}}
td{{padding:6pt 9pt;border:.5pt solid #c0c8d8;vertical-align:top;font-family:Arial}}
tr:nth-child(even) td{{background:#f4f6fb}}
.cover{{text-align:center;padding:0 0 24pt;border-bottom:2pt solid #1a3a6b;margin-bottom:24pt}}
.topbar{{display:flex;justify-content:space-between;align-items:center;padding:4pt 0 8pt;border-bottom:1pt solid #c0cce0;margin-bottom:0}}
.cov-logo-client{{height:44pt;width:auto;max-width:200pt;object-fit:contain}}
.cov-logo-placeholder{{color:#aaa;font-style:italic;font-size:9pt}}
.cov-logo-toledo{{height:44pt;width:auto;object-fit:contain}}
.cov-banner{{width:100%;height:auto;display:block;margin:8pt 0 16pt}}
.cov-title{{font-family:"Arial Black",Arial;font-size:22pt;font-weight:bold;color:#1A3A6B;margin-bottom:6pt}}
.cov-sub{{font-size:11pt;color:#444;margin-bottom:18pt}}
.cov-client{{font-family:"Arial Black",Arial;font-size:16pt;font-weight:bold;color:#1A3A6B;margin-bottom:3pt}}
.cov-unit{{font-size:11pt;color:#666;margin-bottom:14pt}}
.cov-client-img{{width:100%;max-height:160pt;object-fit:cover;border-radius:4pt;margin:12pt 0}}
.pbk{{page-break-after:always}}
a{{color:#1a3a6b}}
.note{{background:#fff8e1;border-left:3pt solid #f5a623;padding:8pt 12pt;margin:10pt 0;font-size:10pt}}
.obs{{background:#e8f4fd;border-left:3pt solid #2980b9;padding:8pt 12pt;margin:10pt 0;font-size:10pt}}
</style></head><body><div class="pg">

<div class="cover">
    {_banner_html}
  <div class="cov-title">DESCRITIVO FUNCIONAL</div>
  <div class="cov-sub">GUARDIAN PRO — Software para Gerenciamento de Operações de Pesagem</div>
  <div class="cov-client">{client_name}{" — " + client_city if client_city else ""}</div>
  {_unit_html}
  {_cimg_html}
  <table style="width:auto;margin:14pt auto"><tbody>{''.join(id_rows)}</tbody></table>
  <p style="font-size:9pt;color:#888"><a href="http://www.toledobrasil.com/produto/guardian">www.toledobrasil.com/produto/guardian</a></p>
</div>
<div class="pbk"></div>

{html_content}

</div></body></html>"""
    return html

# ── Pós-processamento: formatação Toledo no DOCX gerado pelo LibreOffice ──
# Usa lxml + addprevious() para inserir elementos na posição EXATA do schema OOXML

from lxml import etree as _ET

_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# Elementos que vêm APÓS shd no schema CT_PPr
_AFTER_SHD = {'tabs','suppressAutoHyphens','kinsoku','wordWrap','overflowPunct',
    'topLinePunct','autoSpaceDE','autoSpaceDN','bidi','adjustRightInd','snapToGrid',
    'spacing','ind','contextualSpacing','mirrorIndents','suppressOverlap','jc',
    'textDirection','textAlignment','textboxTightWrap','outlineLvl','divId',
    'cnfStyle','rPr','sectPr','pPrChange'}
_AFTER_PBDR = {'shd'} | _AFTER_SHD

# Elementos que vêm APÓS shd no schema CT_TcPr
_AFTER_TCPR_SHD = {'noWrap','tcMar','textDirection','tcFitText','vAlign',
                   'hideMark','headers','tcPrChange'}

def _first_child_in(parent, tag_set):
    for child in parent:
        if not isinstance(child.tag, str): continue
        if _ET.QName(child.tag).localname in tag_set:
            return child
    return None

def _insert_ppr(ppr, new_elem, after_set):
    for e in ppr.findall(new_elem.tag): ppr.remove(e)
    anchor = _first_child_in(ppr, after_set)
    if anchor is not None: anchor.addprevious(new_elem)
    else: ppr.append(new_elem)

def _insert_tcpr_shd(tcpr, hex_color):
    new_shd = _ET.Element(f'{{{_W}}}shd')
    new_shd.set(f'{{{_W}}}val','clear')
    new_shd.set(f'{{{_W}}}color','auto')
    new_shd.set(f'{{{_W}}}fill', hex_color)
    for e in tcpr.findall(f'{{{_W}}}shd'): tcpr.remove(e)
    anchor = _first_child_in(tcpr, _AFTER_TCPR_SHD)
    if anchor is not None: anchor.addprevious(new_shd)
    else: tcpr.append(new_shd)

def _make_shd(hex_color):
    s = _ET.Element(f'{{{_W}}}shd')
    s.set(f'{{{_W}}}val','clear'); s.set(f'{{{_W}}}color','auto')
    s.set(f'{{{_W}}}fill', hex_color)
    return s

def _make_pbdr(color='2E75B6'):
    p = _ET.Element(f'{{{_W}}}pBdr')
    b = _ET.SubElement(p, f'{{{_W}}}bottom')
    b.set(f'{{{_W}}}val','single'); b.set(f'{{{_W}}}sz','4')
    b.set(f'{{{_W}}}space','1'); b.set(f'{{{_W}}}color', color)
    return p

def _apply_toledo_formatting(docx_path, logo_client_b64=""):
    from docx import Document as _Doc
    from docx.shared import Pt as _Pt, RGBColor as _RGB
    from docx.enum.text import WD_ALIGN_PARAGRAPH as _AL
    import io as _io

    doc = _Doc(str(docx_path))

    for para in doc.paragraphs:
        sname = (para.style.name or '') if para.style else ''
        sl = sname.lower()
        ppr = para._p.find(f'{{{_W}}}pPr')
        if ppr is None: continue

        if 'heading 1' in sl or sname in {'Heading1','Ttulo1'}:
            _insert_ppr(ppr, _make_shd('1A3A6B'), _AFTER_SHD)
            para.alignment = _AL.LEFT
            para.paragraph_format.space_before = _Pt(10)
            para.paragraph_format.space_after  = _Pt(5)
            for r in para.runs:
                r.font.color.rgb = _RGB(0xFF,0xFF,0xFF)
                r.font.name = 'Arial Black'
                r.font.size = _Pt(13)
                r.font.bold = True

        elif 'heading 2' in sl or sname in {'Heading2','Ttulo2'}:
            _insert_ppr(ppr, _make_pbdr(), _AFTER_PBDR)
            para.alignment = _AL.LEFT
            para.paragraph_format.space_before = _Pt(8)
            para.paragraph_format.space_after  = _Pt(4)
            for r in para.runs:
                r.font.color.rgb = _RGB(0x2E,0x75,0xB6)
                r.font.name = 'Arial Black'
                r.font.size = _Pt(12)

        else:
            if para.alignment is None:
                para.alignment = _AL.JUSTIFY
            for r in para.runs:
                if not r.font.name: r.font.name = 'Arial'
                if not r.font.size: r.font.size = _Pt(11)

    # Encontrar posição do primeiro H1 para identificar tabela da capa
    first_h1_idx = None
    for pi, para in enumerate(doc.paragraphs):
        if 'heading 1' in ((para.style.name or '') if para.style else '').lower():
            first_h1_idx = pi; break

    for ti, table in enumerate(doc.tables):
        # Detectar se é tabela da capa: vem antes do primeiro H1
        # Localizar posição da tabela no documento
        tbl_elem = table._tbl
        is_cover_table = False
        if first_h1_idx is not None:
            # Verificar se a tabela está antes do primeiro H1 no XML
            body = tbl_elem.getparent()
            if body is not None:
                children = list(body)
                tbl_pos = children.index(tbl_elem) if tbl_elem in children else 999
                # Encontrar posição do primeiro H1
                h1_pos = 999
                for child in children:
                    if child.tag == f'{{{_W}}}p':
                        ppr = child.find(f'{{{_W}}}pPr')
                        if ppr is not None:
                            ps = ppr.find(f'{{{_W}}}pStyle')
                            if ps is not None and 'Heading1' in ps.get(f'{{{_W}}}val',''):
                                h1_pos = children.index(child); break
                is_cover_table = tbl_pos < h1_pos

        for ri, row in enumerate(table.rows):
            for ci, cell in enumerate(row.cells):
                if is_cover_table:
                    # Tabela da capa: col esq = label (cinza), col dir = valor (branco)
                    color = 'EDF0F7' if ci == 0 else ('FFFFFF' if ri%2==0 else 'F4F6FB')
                    is_hdr = False
                else:
                    is_hdr = ri == 0
                    color = '4472C4' if is_hdr else ('FFFFFF' if ri%2==1 else 'F2F2F2')
                tcpr = cell._tc.find(f'{{{_W}}}tcPr')
                if tcpr is None:
                    tcpr = _ET.SubElement(cell._tc, f'{{{_W}}}tcPr')
                _insert_tcpr_shd(tcpr, color)
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.name = 'Arial'
                        r.font.size = _Pt(10)
                        if is_hdr:
                            r.font.color.rgb = _RGB(0xFF,0xFF,0xFF)
                            r.font.bold = True
                        elif is_cover_table and ci == 0:
                            r.font.bold = True

    buf = _io.BytesIO()
    doc.save(buf)
    return _fix_settings(buf.getvalue(), logo_client_b64=logo_client_b64)

def _make_header_xml(logo_client_b64, logo_toledo_b64, rId_client, rId_toledo):
    """Gera o XML do cabeçalho com logos cliente (esq) e Toledo (dir)"""
    WNS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    WPNS = 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
    ANS = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    PICNS = 'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'

    def inline_img(rId, cx, cy, desc, img_id):
        return f"""<wp:inline distT="0" distB="0" distL="0" distR="0">
          <wp:extent cx="{cx}" cy="{cy}"/>
          <wp:effectExtent l="0" t="0" r="0" b="0"/>
          <wp:docPr id="{img_id}" name="{desc}"/>
          <wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>
          <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
            <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
              <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
                <pic:nvPicPr>
                  <pic:cNvPr id="{img_id}" name="{desc}"/>
                  <pic:cNvPicPr><a:picLocks noChangeAspect="1" noChangeArrowheads="1"/></pic:cNvPicPr>
                </pic:nvPicPr>
                <pic:blipFill>
                  <a:blip r:embed="{rId}"/>
                  <a:stretch><a:fillRect/></a:stretch>
                </pic:blipFill>
                <pic:spPr bwMode="auto">
                  <a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
                  <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
                  <a:noFill/>
                  <a:ln><a:noFill/></a:ln>
                </pic:spPr>
              </pic:pic>
            </a:graphicData>
          </a:graphic>
        </wp:inline>"""

    # Toledo logo: 4.86cm x 2.04cm → EMU (1cm = 914400/100 = 9144... 1cm = 360000 EMU)
    # 1 cm = 360000 EMU
    cx_toledo = int(4.86 * 360000)   # 1749600
    cy_toledo = int(2.04 * 360000)   # 734400
    # Logo cliente placeholder: mesmo tamanho
    cx_client = int(3.0 * 360000)    # 1080000
    cy_client = int(2.04 * 360000)   # 734400

    # Se tem logo cliente, usa imagem; senão, texto placeholder
    if logo_client_b64 and rId_client:
        cell_left = f"""<w:p><w:pPr><w:jc w:val="left"/></w:pPr>
        <w:r><w:rPr><w:noProof/></w:rPr>
          <w:drawing>{inline_img(rId_client, cx_client, cy_client, "Logo Cliente", 10)}</w:drawing>
        </w:r></w:p>"""
    else:
        cell_left = """<w:p><w:pPr><w:jc w:val="left"/></w:pPr>
        <w:r><w:rPr>
          <w:rFonts w:ascii="Arial" w:hAnsi="Arial"/>
          <w:color w:val="AAAAAA"/><w:sz w:val="18"/>
        </w:rPr><w:t>(logo do cliente)</w:t></w:r></w:p>"""

    cell_right = f"""<w:p><w:pPr><w:jc w:val="right"/></w:pPr>
      <w:r><w:rPr><w:noProof/></w:rPr>
        <w:drawing>{inline_img(rId_toledo, cx_toledo, cy_toledo, "Toledo do Brasil", 11)}</w:drawing>
      </w:r></w:p>"""

    # Linha separadora abaixo do cabeçalho
    sep_line = """<w:p><w:pPr>
      <w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="C0C8D8"/></w:pBdr>
    </w:pPr></w:p>"""

    xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr {WNS} {RNS} {WPNS} {ANS} {PICNS}
    xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">
  <w:tbl>
    <w:tblPr>
      <w:tblW w:w="0" w:type="auto"/>
      <w:tblBorders>
        <w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:bottom w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>
      </w:tblBorders>
    </w:tblPr>
    <w:tblGrid>
      <w:gridCol w:w="4500"/>
      <w:gridCol w:w="4500"/>
    </w:tblGrid>
    <w:tr>
      <w:tc>
        <w:tcPr><w:tcW w:w="4500" w:type="dxa"/><w:vAlign w:val="center"/></w:tcPr>
        {cell_left}
      </w:tc>
      <w:tc>
        <w:tcPr><w:tcW w:w="4500" w:type="dxa"/><w:vAlign w:val="center"/></w:tcPr>
        {cell_right}
      </w:tc>
    </w:tr>
  </w:tbl>
  {sep_line}
</w:hdr>"""
    return xml.encode('utf-8')


def _make_toc_xml():
    """Gera o XML do índice (TOC) que o Word atualiza automaticamente"""
    return """<w:p>
  <w:pPr><w:pStyle w:val="TOCHeading"/><w:spacing w:before="240" w:after="120"/></w:pPr>
  <w:r><w:rPr><w:rFonts w:ascii="Arial Black" w:hAnsi="Arial Black"/><w:b/><w:color w:val="1A3A6B"/><w:sz w:val="28"/></w:rPr>
    <w:t>Índice</w:t>
  </w:r>
</w:p>
<w:p>
  <w:pPr><w:spacing w:before="0" w:after="0"/></w:pPr>
  <w:fldSimple w:instr=" TOC \\o &quot;1-2&quot; \\h \\z \\u ">
    <w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="20"/><w:color w:val="1A3A6B"/></w:rPr>
      <w:t>Clique com botão direito e &quot;Atualizar campo&quot; para gerar o índice.</w:t>
    </w:r>
  </w:fldSimple>
</w:p>
<w:p><w:pPr><w:pageBreakBefore/><w:spacing w:before="0" w:after="0"/></w:pPr></w:p>"""


def _fix_settings(docx_bytes, logo_client_b64='', logo_toledo_b64=''):
    buf_in=io.BytesIO(docx_bytes); buf_out=io.BytesIO()
    
    with zipfile.ZipFile(buf_in,'r') as zi:
        # Ler todos os arquivos
        all_files = {item.filename: zi.read(item.filename) for item in zi.infolist()}
    
    # ── Preparar imagens para o cabeçalho ──
    imgs_raw = extract_imgs_from_builder()
    toledo_png = imgs_raw.get('logo_toledo_real', b'')
    
    # IDs dos relacionamentos do cabeçalho
    rId_toledo = 'rHdr1'
    rId_client = 'rHdr2' if logo_client_b64 else ''
    
    # ── Gerar header1.xml ──
    header_xml = _make_header_xml(logo_client_b64, logo_toledo_b64, rId_client, rId_toledo)
    all_files['word/header1.xml'] = header_xml
    
    # ── Gerar header1.xml.rels ──
    rels_hdr = [
        f'<Relationship Id="{rId_toledo}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="media/image_toledo_hdr.jpeg"/>',
    ]
    if logo_client_b64 and rId_client:
        rels_hdr.append(
            f'<Relationship Id="{rId_client}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="media/image_client_hdr.png"/>'
        )
    hdr_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(rels_hdr) +
        '</Relationships>'
    ).encode('utf-8')
    all_files['word/_rels/header1.xml.rels'] = hdr_rels_xml
    
    # ── Salvar logo Toledo na pasta media do header ──
    if toledo_png:
        all_files['word/media/image_toledo_hdr.jpeg'] = toledo_png
    
    # ── Salvar logo cliente se fornecido ──
    if logo_client_b64:
        try:
            import base64 as _b64
            client_data = _b64.b64decode(logo_client_b64.split(",",1)[-1])
            all_files['word/media/image_client_hdr.png'] = client_data
        except: pass
    
    # ── Atualizar document.xml.rels para incluir header ──
    rels_doc = all_files.get('word/_rels/document.xml.rels', b'').decode('utf-8')
    if 'header1.xml' not in rels_doc:
        rels_doc = rels_doc.replace(
            '</Relationships>',
            '<Relationship Id="rHdrMain" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
            'Target="header1.xml"/></Relationships>'
        )
    all_files['word/_rels/document.xml.rels'] = rels_doc.encode('utf-8')
    
    # ── Atualizar document.xml: sectPr + TOC ──
    doc_xml = all_files.get('word/document.xml', b'').decode('utf-8')
    
    # Adicionar headerReference no sectPr
    if 'w:headerReference' not in doc_xml:
        doc_xml = doc_xml.replace(
            '<w:type w:val="nextPage"/>',
            '<w:headerReference w:type="default" r:id="rHdrMain"/>'
            '<w:type w:val="nextPage"/>'
        )
        # Se não tinha <w:type>, tentar outro ponto
        if 'w:headerReference' not in doc_xml:
            doc_xml = re.sub(
                r'(<w:sectPr[^>]*>)',
                r'\1<w:headerReference w:type="default" r:id="rHdrMain"/>',
                doc_xml
            )
    
    # Aumentar margem do topo para cabeçalho (header=851=1.5cm, top=851)
    doc_xml = re.sub(
        r'w:header="[^"]*"',
        'w:header="851"',
        doc_xml
    )
    doc_xml = re.sub(
        r'(w:top=")567(")',
        r'\g<1>1417\g<2>',  # 2.5cm top margin
        doc_xml
    )
    
    # Inserir TOC após o page-break da capa (primeiro <w:p> com pageBreakBefore ou após pbk)
    # O documento tem: capa → <p pageBreakBefore> → conteúdo
    # Inserir TOC + page-break APÓS o primeiro page-break
    toc_xml = _make_toc_xml()
    # Inserir TOC: buscar page-break da capa ou primeiro H1
    pbk_idx = doc_xml.find('<w:pageBreakBefore/>')
    h1_idx  = doc_xml.find('<w:pStyle w:val="Heading1"/>')
    if pbk_idx > 0:
        end_p = doc_xml.find('</w:p>', pbk_idx)
        if end_p > 0:
            insert_pos = end_p + len('</w:p>')
            doc_xml = doc_xml[:insert_pos] + toc_xml + doc_xml[insert_pos:]
    elif h1_idx > 0:
        start_p = doc_xml.rfind('<w:p>', 0, h1_idx)
        if start_p > 0:
            doc_xml = doc_xml[:start_p] + toc_xml + '<w:p><w:pPr><w:pageBreakBefore/></w:pPr></w:p>' + doc_xml[start_p:]
    all_files['word/document.xml'] = doc_xml.encode('utf-8')
    
    # ── Processar demais arquivos (settings, styles) ──
    if 'word/settings.xml' in all_files:
        xml = all_files['word/settings.xml'].decode('utf-8')
        xml = re.sub(r'<w:zoom([^>]*)/>', 
            lambda m: f'<w:zoom{m.group(1)} w:percent="100"/>' if 'percent' not in m.group(1) else m.group(0), xml)
        all_files['word/settings.xml'] = xml.encode('utf-8')
    
    if 'word/styles.xml' in all_files:
        xml = all_files['word/styles.xml'].decode('utf-8')
        xml = xml.replace('w:ascii="Arial Black;Arial"','w:ascii="Arial Black"')
        xml = xml.replace('w:hAnsi="Arial Black;Arial"','w:hAnsi="Arial Black"')
        xml = xml.replace('w:eastAsia="Arial Black;Arial"','w:eastAsia="Arial Black"')
        xml = xml.replace('w:cs="Arial Black;Arial"','w:cs="Arial Black"')
        xml = re.sub(r'(<w:style[^>]*styleId="Heading1".*?<w:pPr>.*?)<w:ind[^/]*/>', r'\1<w:ind w:left="0" w:right="0"/>', xml, flags=re.DOTALL)
        xml = re.sub(r'(<w:style[^>]*styleId="Heading1".*?)<w:pBdr/>', r'\1', xml, flags=re.DOTALL)
        # Adicionar estilo TOCHeading se não existir
        if 'TOCHeading' not in xml:
            toc_style = """<w:style w:type="paragraph" w:styleId="TOCHeading">
  <w:name w:val="TOC Heading"/>
  <w:basedOn w:val="Normal"/>
  <w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>
  <w:rPr><w:rFonts w:ascii="Arial Black" w:hAnsi="Arial Black"/><w:b/><w:color w:val="1A3A6B"/><w:sz w:val="26"/></w:rPr>
</w:style>"""
            xml = xml.replace('</w:styles>', toc_style + '</w:styles>')
        all_files['word/styles.xml'] = xml.encode('utf-8')
    
    # ── Remontar o ZIP ──
    with zipfile.ZipFile(buf_out,'w',zipfile.ZIP_DEFLATED) as zo:
        for fname, data in all_files.items():
            zo.writestr(fname, data)
    
    return buf_out.getvalue()


# ── GERADOR PRINCIPAL ─────────────────────────────────────────
def generate_docx(data, imgs):
    doc = Document()
    for section in doc.sections:
        section.page_width    = Cm(21)
        section.page_height   = Cm(29.7)
        section.left_margin   = Cm(1.9)
        section.right_margin  = Cm(1.9)
        section.top_margin    = Cm(2.5)
        section.bottom_margin = Cm(2.5)
    doc.styles['Normal'].font.name = 'Arial'
    doc.styles['Normal'].font.size = Pt(11)

    # ── CAPA ──
    # Tabela topo: logo cliente (esq) | logo Toledo (dir)
    tbl_top = doc.add_table(rows=1, cols=2)
    remove_table_borders(tbl_top._tbl)
    c_l = tbl_top.rows[0].cells[0]; c_l.width = Cm(8.27)
    c_r = tbl_top.rows[0].cells[1]; c_r.width = Cm(9.00)

    # Logo cliente
    if data.get('clientLogoB64'):
        try:
            logo_data = base64.b64decode(data['clientLogoB64'].split(',',1)[1])
            p_l = c_l.paragraphs[0]; p_l.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p_l.add_run().add_picture(io.BytesIO(logo_data), height=Cm(2.04))
        except:
            _placeholder_logo(c_l)
    else:
        _placeholder_logo(c_l)

    # Logo Toledo
    p_r = c_r.paragraphs[0]; p_r.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    if 'logo_toledo_real' in imgs:
        p_r.add_run().add_picture(io.BytesIO(imgs['logo_toledo_real']),
                                   width=Cm(4.86), height=Cm(2.04))
    else:
        r = p_r.add_run('Toledo do Brasil')
        r.font.name='Arial Black'; r.font.size=Pt(14)
        r.font.bold=True; r.font.color.rgb=C_AZUL_MED

    # Espaço
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # Banner Guardian — 18.43×7.72cm, LEFT
    p_banner = doc.add_paragraph()
    p_banner.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_banner.paragraph_format.space_before = Pt(2)
    p_banner.paragraph_format.space_after  = Pt(10)
    if 'guardian_capa' in imgs:
        p_banner.add_run().add_picture(io.BytesIO(imgs['guardian_capa']),
                                        width=Cm(18.43), height=Cm(7.72))

    # Título
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run('DESCRITIVO FUNCIONAL')
    r.font.name='Arial Black'; r.font.size=Pt(22)
    r.font.bold=True; r.font.color.rgb=C_AZUL

    # Subtítulo
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(14)
    r = p.add_run('GUARDIAN PRO — Software para Gerenciamento de Operações de Pesagem')
    r.font.name='Arial'; r.font.size=Pt(12)
    r.font.color.rgb=RGBColor(0x44,0x44,0x44)

    # Nome cliente
    client_str = (data.get('clientName','') or '').upper()
    if data.get('clientCity'): client_str += f" — {data['clientCity'].upper()}"
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(client_str)
    r.font.name='Arial Black'; r.font.size=Pt(16)
    r.font.bold=True; r.font.color.rgb=C_AZUL

    if data.get('clientUnit'):
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(16)
        r = p.add_run(data['clientUnit'])
        r.font.name='Cambria'; r.font.size=Pt(13)
        r.font.color.rgb=RGBColor(0x66,0x66,0x66)

    # Tabela identificação
    rows_id = [
        ('CT / OV Hardware e Serviços', data.get('ctHardware','A definir')),
        ('Licenciamento Cloud',          data.get('ctCloud','A definir')),
        ('Analista Responsável',         data.get('analystName','—')),
        ('Revisão',                      data.get('docRevision','Rev00')),
        ('Data do Documento',            data.get('docDate','—')),
    ]
    if data.get('clientFilial'):
        rows_id.insert(2, ('Filial(is)', data['clientFilial']))
    make_table(doc, ['Campo','Valor'], rows_id, [5.5, 9.77])

    # URL
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    r = p.add_run('www.toledobrasil.com/produto/guardian')
    r.font.name='Arial'; r.font.size=Pt(9)
    r.font.italic=True; r.font.color.rgb=C_AZUL

    doc.add_page_break()

    # ── HISTÓRICO DE REVISÕES ──
    add_h1(doc, 'Informações do Documento')
    make_table(doc,
        ['Data','Revisão','Descrição','Analista'],
        [[data.get('docDate','—'), data.get('docRevision','Rev00'),
          data.get('revDesc','Geração do documento'), data.get('analystName','—')]],
        [2.5, 1.5, 8.27, 3.0])
    doc.add_page_break()

    # ── CONTEÚDO PRINCIPAL ──
    if data.get('htmlContent'):
        parse_html_content(doc, data['htmlContent'])

    # Salvar
    buf = io.BytesIO()
    doc.save(buf)
    return _fix_settings(buf.getvalue())

def _placeholder_logo(cell):
    p = cell.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run('(logo do cliente)')
    r.font.italic=True; r.font.size=Pt(9)
    r.font.color.rgb=RGBColor(0xAA,0xAA,0xAA)


# ── SERVIDOR HTTP ─────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  [{args[1]}] {args[0]}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if self.path == '/convert':
            # Recebe MHT do browser, converte para DOCX via LibreOffice
            length = int(self.headers.get('Content-Length', 0))
            mht_data = self.rfile.read(length)
            tmp_dir = out_dir = None
            try:
                tmp_dir = tempfile.mkdtemp()
                mht_path = os.path.join(tmp_dir, 'descritivo.mht')
                with open(mht_path, 'wb') as f:
                    f.write(mht_data)
                out_dir = tempfile.mkdtemp()
                # Configurar ambiente para LibreOffice no container Railway
                lo_home = tempfile.mkdtemp(prefix='lo_home_')
                lo_env = os.environ.copy()
                lo_env['HOME'] = lo_home
                lo_env['TMPDIR'] = lo_home

                result = subprocess.run(
                    ['soffice',
                     '--headless',
                     '--norestore',
                     '--nofirststartwizard',
                     '--nolockcheck',
                     '--convert-to', 'docx',
                     '--outdir', out_dir,
                     mht_path],
                    capture_output=True, text=True,
                    timeout=120, env=lo_env
                )
                # Limpar HOME temporário do LibreOffice
                shutil.rmtree(lo_home, ignore_errors=True)
                docx_files = list(Path(out_dir).glob('*.docx'))
                if not docx_files:
                    raise Exception(f'LibreOffice falhou: {result.stderr[:300]}')
                # Pós-processamento: aplicar formatação Toledo via python-docx
                docx_bytes = _apply_toledo_formatting(docx_files[0], logo_client_b64=data.get('clientLogoB64',''))
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                self.send_header('Content-Length', len(docx_bytes))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(docx_bytes)
                print(f'  ✓ MHT→DOCX: {len(docx_bytes)//1024}KB')
            except subprocess.TimeoutExpired:
                print('  ✗ LibreOffice timeout')
                self._error('Timeout na conversão — tente novamente')
            except Exception as e:
                import traceback
                print(f'  ✗ Erro conversão: {e}')
                traceback.print_exc()
                self._error(str(e))
            finally:
                if tmp_dir: shutil.rmtree(tmp_dir, ignore_errors=True)
                if out_dir: shutil.rmtree(out_dir, ignore_errors=True)

        elif self.path == '/generate':
            # Recebe JSON → gera DOCX via python-docx puro (sem LibreOffice)
            if not _DOCX_AVAILABLE:
                self._error('python-docx não disponível no servidor. Verifique requirements.txt.')
                return
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            try:
                data = json.loads(body)

                # Carregar imagens Toledo do builder HTML
                imgs        = extract_imgs_from_builder()
                toledo_logo = imgs.get('logo_toledo_real', b'')
                guardian_bn = imgs.get('guardian_capa',    b'')

                # Gerar DOCX puro
                docx_bytes = build_docx_pure(data, toledo_logo, guardian_bn)

                self.send_response(200)
                self.send_header('Content-Type',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                self.send_header('Content-Length', len(docx_bytes))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(docx_bytes)
                print(f'  ✓ DOCX puro: {len(docx_bytes)//1024}KB')

                # Salvar no histórico (silencioso em caso de falha)
                try:
                    _salvar_projeto(data)
                except Exception as _dbe:
                    print(f'  [DB] Aviso: {_dbe}')

            except Exception as e:
                import traceback; traceback.print_exc()
                self._error(str(e))

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        path = self.path.split('?')[0]
        qs   = parse_qs(urlparse(self.path).query)

        # ── Builder (rota principal) ──────────────────────────────
        if path in ('/', '/builder'):
            try:
                content = BUILDER_HTML.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, 'builder-descritivo.html nao encontrado')

        # ── Histórico: listar ─────────────────────────────────────
        elif path == '/projetos':
            analista = qs.get('analista', [''])[0]
            busca    = qs.get('busca',    [''])[0]
            projetos = _listar_projetos(analista=analista, busca=busca)
            body = json.dumps({'projetos': projetos}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        # ── Histórico: clonar ─────────────────────────────────────
        elif path == '/projetos/clonar':
            proj_id = qs.get('id', [''])[0]
            payload = _carregar_projeto(proj_id) if proj_id else None
            if payload:
                body = json.dumps({'ok': True, 'payload': payload}, ensure_ascii=False).encode()
                self.send_response(200)
            else:
                body = json.dumps({'ok': False, 'erro': 'Projeto nao encontrado'}).encode()
                self.send_response(404)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        # ── Histórico: excluir ────────────────────────────────────
        elif path == '/projetos/excluir':
            proj_id = qs.get('id', [''])[0]
            ok = _excluir_projeto(proj_id) if proj_id else False
            body = json.dumps({'ok': ok}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(body))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        # ── Health check ──────────────────────────────────────────
        elif path == '/ping':
            body = b'pong'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)

        # ── Changelog ─────────────────────────────────────────────
        elif path == '/changelog':
            changelog_file = HERE / 'changelog.json'
            if changelog_file.exists():
                try:
                    data = changelog_file.read_bytes()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Content-Length', len(data))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as e:
                    self._error(str(e))
            else:
                body = b'[]'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', len(body))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(body)

        # ── Status do banco de dados ───────────────────────────────
        elif path == '/db-status':
            db_url = os.environ.get('DATABASE_URL', '')
            if not db_url:
                status = {'ok': False, 'erro': 'DATABASE_URL não configurada. Adicione o PostgreSQL no Railway.'}
            else:
                try:
                    conn = _get_db()
                    if conn:
                        cur = conn.cursor()
                        cur.execute("SELECT COUNT(*) FROM projetos WHERE status='ativo'")
                        total = cur.fetchone()[0]
                        cur.close(); conn.close()
                        status = {'ok': True, 'total_projetos': total, 'banco': 'conectado'}
                    else:
                        status = {'ok': False, 'erro': 'Falha ao conectar no banco'}
                except Exception as e:
                    status = {'ok': False, 'erro': str(e)}
            body = json.dumps(status, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()

    def send_header_cors(self):
        """Helper para não repetir CORS em toda rota."""
        pass  # CORS é adicionado nas respostas individualmente

    def _error(self, msg):
        self.send_response(500)
        data = msg.encode('utf-8')
        self.send_header('Content-Type','text/plain; charset=utf-8')
        self.send_header('Content-Length', len(data))
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    _init_db()  # Garante tabela no PostgreSQL
    import socketserver

    print()
    print('  Construtor de Descritivo Funcional — Servidor iniciando...')
    print(f'  Porta: {PORT}')
    print(f'  builder.html: {"OK" if BUILDER_HTML.exists() else "NAO ENCONTRADO"}')
    db_url = os.environ.get('DATABASE_URL', '')
    if db_url:
        print('  DATABASE_URL: configurada ✓')
    else:
        print('  DATABASE_URL: NÃO configurada — histórico desativado')
        print('  → Adicione PostgreSQL no Railway para habilitar o histórico')
    print()

    if not BUILDER_HTML.exists():
        print(f'  [ERRO] builder-descritivo.html nao encontrado em {BUILDER_HTML.parent}')
        sys.exit(1)

    import signal
    def shutdown(signum, frame):
        print('\n  Encerrando servidor...')
        sys.exit(0)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(('0.0.0.0', PORT), Handler) as httpd:
            print(f'  Servidor rodando na porta {PORT}')
            httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n  Servidor encerrado.')
    except OSError as e:
        print(f'\n  [ERRO] Porta {PORT}: {e}')
        sys.exit(1)
    