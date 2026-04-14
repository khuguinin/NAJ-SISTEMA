"""
Sistema de Controle de Processos – v4.0 CLOUD
Núcleo de Assistência Jurídica à População de Baixa Renda
Prefeitura Municipal de Iúna/ES

Versão online: Streamlit Cloud + Supabase (PostgreSQL)
"""

import streamlit as st
import psycopg2
import psycopg2.extras
import hashlib
import datetime
import io
import os
import base64
from contextlib import contextmanager

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURAÇÃO DA PÁGINA
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="NAJ Iúna/ES – Controle de Processos",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
#  USUÁRIOS
# ══════════════════════════════════════════════════════════════════════════════
def _hash(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()

USERS = {
    "portaria": {"senha_hash": _hash("portaria123"), "nome": "Portaria",                         "perfil": "portaria"},
    "kleber":   {"senha_hash": _hash("kleber123"),   "nome": "Kleber Huguinin Barbosa",           "perfil": "assessor"},
    "gustavo":  {"senha_hash": _hash("gustavo123"),  "nome": "Gustavo Almeida Ferreira Bernardo", "perfil": "assessor"},
    "erikson":  {"senha_hash": _hash("erikson123"),  "nome": "Erikson Fernandes Tiradentes",      "perfil": "assessor"},
}

ASSESSORES = [
    "Kleber Huguinin Barbosa",
    "Gustavo Almeida Ferreira Bernardo",
    "Erikson Fernandes Tiradentes",
]

STATUS_PROCESSO = ["Em Andamento", "Aguardando Documentos", "Protocolado", "Arquivado"]
STATUS_DEMANDA  = ["Pendente", "Concluída"]
PRIORIDADES     = ["Alta", "Média", "Baixa"]

# ══════════════════════════════════════════════════════════════════════════════
#  LOGO
# ══════════════════════════════════════════════════════════════════════════════
def _get_logo_b64() -> str:
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_naj.jpg")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

# ══════════════════════════════════════════════════════════════════════════════
#  BANCO DE DADOS  —  Supabase / PostgreSQL
# ══════════════════════════════════════════════════════════════════════════════

@contextmanager
def get_conn():
    """Abre conexão com o Supabase usando a URL armazenada nos secrets do Streamlit."""
    conn = psycopg2.connect(st.secrets["DATABASE_URL"])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _exec(sql: str, params=None):
    """Executa um comando DML (INSERT / UPDATE / DELETE) sem retorno."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)

def _query(sql: str, params=None) -> list[dict]:
    """Executa SELECT e retorna lista de dicts."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

def init_db():
    """Cria as tabelas caso ainda não existam (idempotente)."""
    sqls = [
        """
        CREATE TABLE IF NOT EXISTS processos (
            id             SERIAL PRIMARY KEY,
            data_entrada   TEXT NOT NULL,
            numero_pasta   TEXT DEFAULT '',
            nome_assistido TEXT NOT NULL,
            descricao      TEXT DEFAULT '',
            assessor       TEXT DEFAULT '',
            prioridade     TEXT DEFAULT 'Media',
            status         TEXT DEFAULT 'Em Andamento',
            criado_por     TEXT DEFAULT '',
            criado_em      TEXT DEFAULT '',
            editado_por    TEXT DEFAULT '',
            editado_em     TEXT DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS demandas (
            id               SERIAL PRIMARY KEY,
            data_solicitacao TEXT NOT NULL,
            numero_pasta     TEXT DEFAULT '',
            nome_assistido   TEXT NOT NULL,
            demanda          TEXT DEFAULT '',
            assessor         TEXT DEFAULT '',
            status           TEXT DEFAULT 'Pendente',
            criado_por       TEXT DEFAULT '',
            criado_em        TEXT DEFAULT '',
            editado_por      TEXT DEFAULT '',
            editado_em       TEXT DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS atendimentos (
            id               SERIAL PRIMARY KEY,
            data_atendimento TEXT NOT NULL,
            nome_pessoa      TEXT NOT NULL,
            telefone         TEXT DEFAULT '',
            demanda          TEXT DEFAULT '',
            resolucao        TEXT DEFAULT '',
            assessor         TEXT DEFAULT '',
            criado_por       TEXT DEFAULT '',
            criado_em        TEXT DEFAULT '',
            editado_por      TEXT DEFAULT '',
            editado_em       TEXT DEFAULT ''
        )
        """,
        # Migração segura: adiciona coluna se não existir
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='processos' AND column_name='numero_pasta'
            ) THEN
                ALTER TABLE processos ADD COLUMN numero_pasta TEXT DEFAULT '';
            END IF;
        END $$
        """,
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            for sql in sqls:
                cur.execute(sql)

def agora_str() -> str:
    return datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

def hoje_iso() -> str:
    return datetime.date.today().isoformat()

def fmt_data(iso: str) -> str:
    try:
        return datetime.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except Exception:
        return iso or "—"

def dias_aberto(iso: str) -> int:
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(iso)).days
    except Exception:
        return 0

# ── CRUD Processos ─────────────────────────────────────────────────────────────
def listar_processos(filtro_status=None):
    if filtro_status is None:
        return _query("SELECT * FROM processos ORDER BY data_entrada ASC")
    elif isinstance(filtro_status, list):
        return _query(
            "SELECT * FROM processos WHERE status = ANY(%s) ORDER BY data_entrada ASC",
            (filtro_status,)
        )
    else:
        return _query(
            "SELECT * FROM processos WHERE status=%s ORDER BY data_entrada ASC",
            (filtro_status,)
        )

def inserir_processo(data_entrada, pasta, nome, descricao, assessor, prioridade, usuario):
    _exec(
        "INSERT INTO processos "
        "(data_entrada,numero_pasta,nome_assistido,descricao,assessor,prioridade,status,criado_por,criado_em) "
        "VALUES (%s,%s,%s,%s,%s,%s,'Em Andamento',%s,%s)",
        (data_entrada, pasta, nome, descricao, assessor, prioridade, usuario, agora_str())
    )

def atualizar_processo(pid, data_entrada, pasta, nome, descricao, assessor, prioridade, status, usuario):
    _exec(
        "UPDATE processos SET data_entrada=%s,numero_pasta=%s,nome_assistido=%s,descricao=%s,"
        "assessor=%s,prioridade=%s,status=%s,editado_por=%s,editado_em=%s WHERE id=%s",
        (data_entrada, pasta, nome, descricao, assessor, prioridade, status, usuario, agora_str(), pid)
    )

def alterar_status_processo(pid, status, usuario):
    _exec(
        "UPDATE processos SET status=%s,editado_por=%s,editado_em=%s WHERE id=%s",
        (status, usuario, agora_str(), pid)
    )

def deletar_processo(pid):
    _exec("DELETE FROM processos WHERE id=%s", (pid,))

# ── CRUD Demandas ──────────────────────────────────────────────────────────────
def listar_demandas(filtro_status=None):
    if filtro_status:
        return _query(
            "SELECT * FROM demandas WHERE status=%s ORDER BY data_solicitacao ASC",
            (filtro_status,)
        )
    return _query("SELECT * FROM demandas ORDER BY data_solicitacao ASC")

def inserir_demanda(data_sol, pasta, nome, demanda, assessor, usuario):
    _exec(
        "INSERT INTO demandas "
        "(data_solicitacao,numero_pasta,nome_assistido,demanda,assessor,status,criado_por,criado_em) "
        "VALUES (%s,%s,%s,%s,%s,'Pendente',%s,%s)",
        (data_sol, pasta, nome, demanda, assessor, usuario, agora_str())
    )

def atualizar_demanda(did, data_sol, pasta, nome, demanda, assessor, status, usuario):
    _exec(
        "UPDATE demandas SET data_solicitacao=%s,numero_pasta=%s,nome_assistido=%s,demanda=%s,"
        "assessor=%s,status=%s,editado_por=%s,editado_em=%s WHERE id=%s",
        (data_sol, pasta, nome, demanda, assessor, status, usuario, agora_str(), did)
    )

def deletar_demanda(did):
    _exec("DELETE FROM demandas WHERE id=%s", (did,))

# ── CRUD Atendimentos ──────────────────────────────────────────────────────────
def listar_atendimentos():
    return _query("SELECT * FROM atendimentos ORDER BY data_atendimento DESC")

def inserir_atendimento(data_at, nome, telefone, demanda, resolucao, assessor, usuario):
    _exec(
        "INSERT INTO atendimentos "
        "(data_atendimento,nome_pessoa,telefone,demanda,resolucao,assessor,criado_por,criado_em) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (data_at, nome, telefone, demanda, resolucao, assessor, usuario, agora_str())
    )

def atualizar_atendimento(aid, data_at, nome, telefone, demanda, resolucao, assessor, usuario):
    _exec(
        "UPDATE atendimentos SET data_atendimento=%s,nome_pessoa=%s,telefone=%s,demanda=%s,"
        "resolucao=%s,assessor=%s,editado_por=%s,editado_em=%s WHERE id=%s",
        (data_at, nome, telefone, demanda, resolucao, assessor, usuario, agora_str(), aid)
    )

def deletar_atendimento(aid):
    _exec("DELETE FROM atendimentos WHERE id=%s", (aid,))

# ══════════════════════════════════════════════════════════════════════════════
#  GERAÇÃO DE PDF  (ReportLab – A4 paisagem)
# ══════════════════════════════════════════════════════════════════════════════
def gerar_pdf(titulo: str, dados: list, tipo: str, assessor_filtro: str = "") -> bytes:
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                        Paragraph, Spacer, HRFlowable, Image)
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        return b""

    buf   = io.BytesIO()
    PAGE  = landscape(A4)
    doc   = SimpleDocTemplate(buf, pagesize=PAGE,
                leftMargin=15*mm, rightMargin=15*mm,
                topMargin=15*mm, bottomMargin=12*mm)

    AZUL   = colors.HexColor("#1e3a8a")
    CINZA  = colors.HexColor("#475569")
    HDR_BG = colors.HexColor("#dbeafe")
    ALT_BG = colors.HexColor("#f8fafc")
    BORDA  = colors.HexColor("#cbd5e1")

    def ps(sz=8, bold=False, center=False, color=colors.black, space=0):
        return ParagraphStyle("_",
            fontSize=sz,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            alignment=TA_CENTER if center else TA_LEFT,
            textColor=color,
            spaceAfter=space,
            leading=sz * 1.35,
        )

    def p(txt, **kw):
        return Paragraph(str(txt) if txt else "—", ps(**kw))

    titulo_rel = titulo + (f" — {assessor_filtro.split()[0]}" if assessor_filtro else "")
    story = []

    # Cabeçalho com logo
    logo_b64 = _get_logo_b64()
    if logo_b64:
        try:
            logo_img = Image(io.BytesIO(base64.b64decode(logo_b64)), width=60*mm, height=18*mm)
            hdr = Table([[logo_img,
                          [p("NÚCLEO DE ASSISTÊNCIA JURÍDICA À POPULAÇÃO DE BAIXA RENDA",
                             sz=13, bold=True, center=True, color=AZUL),
                           p("Prefeitura Municipal de Iúna/ES", sz=10, center=True, color=CINZA)]]],
                        colWidths=[65*mm, None])
            hdr.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(0,0),(-1,-1),"CENTER")]))
            story.append(hdr)
        except Exception:
            story.append(p("NÚCLEO DE ASSISTÊNCIA JURÍDICA", sz=14, bold=True, center=True, color=AZUL))
    else:
        story.append(p("NÚCLEO DE ASSISTÊNCIA JURÍDICA À POPULAÇÃO DE BAIXA RENDA",
                       sz=14, bold=True, center=True, color=AZUL))
        story.append(p("Prefeitura Municipal de Iúna/ES", sz=10, center=True, color=CINZA))

    story += [
        Spacer(1, 4*mm),
        HRFlowable(width="100%", thickness=1.5, color=AZUL),
        Spacer(1, 3*mm),
        p(titulo_rel, sz=13, bold=True, center=True, color=AZUL),
        p(f"Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y às %H:%M')}",
          sz=8, center=True, color=CINZA, space=6),
    ]

    if not dados:
        story.append(Spacer(1, 8*mm))
        story.append(p("Nenhum registro encontrado.", sz=11, center=True, color=CINZA))
    elif tipo == "atendimentos":
        for i, item in enumerate(dados, 1):
            bloco = [
                [p(f"{i}. {item.get('nome_pessoa','—')}", sz=9, bold=True), ""],
                [p(f"Data: {fmt_data(item.get('data_atendimento',''))}  |  "
                   f"Tel: {item.get('telefone','—') or '—'}  |  "
                   f"Assessor: {item.get('assessor','—') or '—'}", sz=8), ""],
                [p(f"Demanda: {item.get('demanda','—') or '—'}", sz=8), ""],
                [p(f"Resolução: {item.get('resolucao','—') or '—'}", sz=8), ""],
            ]
            PW = PAGE[0] - 30*mm
            t  = Table(bloco, colWidths=[PW * 0.4, PW * 0.6])
            t.setStyle(TableStyle([
                ("SPAN",(0,0),(1,0)), ("SPAN",(0,1),(1,1)), ("SPAN",(0,2),(1,2)), ("SPAN",(0,3),(1,3)),
                ("BOX",(0,0),(-1,-1),0.5,BORDA), ("BACKGROUND",(0,0),(-1,0),ALT_BG),
                ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
                ("LEFTPADDING",(0,0),(-1,-1),6),
            ]))
            story.append(t)
            story.append(Spacer(1, 3))
    else:
        if "processos" in tipo:
            headers = ["#ID","Entrada","Pasta","Assistido","Descrição","Assessor","Prioridade","Status"]
            col_w   = [14*mm, 22*mm, 22*mm, 50*mm, 65*mm, 35*mm, 20*mm, 30*mm]
            def row_fn(r):
                return [
                    p(f"#{r['id']}", bold=True),
                    p(fmt_data(r.get("data_entrada",""))),
                    p(r.get("numero_pasta","") or "—"),
                    p(r.get("nome_assistido","—")),
                    p((r.get("descricao","") or "—")[:55]),
                    p((r.get("assessor","") or "—").split()[0]),
                    p(r.get("prioridade","—")),
                    p(r.get("status","—")),
                ]
        else:
            headers = ["#ID","Data","Pasta","Assistido","Demanda","Assessor","Status"]
            col_w   = [14*mm, 22*mm, 22*mm, 55*mm, 90*mm, 40*mm, 26*mm]
            def row_fn(r):
                return [
                    p(f"#{r['id']}", bold=True),
                    p(fmt_data(r.get("data_solicitacao",""))),
                    p(r.get("numero_pasta","") or "—"),
                    p(r.get("nome_assistido","—")),
                    p((r.get("demanda","") or "—")[:65]),
                    p((r.get("assessor","") or "—").split()[0]),
                    p(r.get("status","—")),
                ]

        table_data = [[p(h, bold=True) for h in headers]] + [row_fn(r) for r in dados]
        t = Table(table_data, colWidths=col_w, repeatRows=1)
        sty = TableStyle([
            ("BACKGROUND",(0,0),(-1,0),HDR_BG),
            ("GRID",(0,0),(-1,-1),0.35,BORDA),
            ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LEFTPADDING",(0,0),(-1,-1),4), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ])
        for i in range(2, len(table_data), 2):
            sty.add("BACKGROUND",(0,i),(-1,i),ALT_BG)
        t.setStyle(sty)
        story.append(t)

    story += [
        Spacer(1, 6*mm),
        p(f"Total de registros: {len(dados)}", sz=9, bold=True, color=AZUL),
        Spacer(1, 3*mm),
        HRFlowable(width="100%", thickness=0.5, color=BORDA),
        Spacer(1, 2*mm),
        p("Sistema de Controle de Processos • Núcleo de Assistência Jurídica • Iúna/ES",
          sz=7, center=True, color=CINZA),
    ]
    doc.build(story)
    return buf.getvalue()

def _get_dados_relatorio(tipo, assessor_filtro, data_ini=None, data_fim=None):
    """Retorna (dados, titulo). Filtra por assessor e/ou intervalo de datas."""
    labels = {
        "processos_ativos":       "Processos Ativos",
        "processos_aguardando":   "Processos Aguardando Documentos",
        "processos_protocolados": "Processos Protocolados",
        "processos_arquivados":   "Procedimentos Arquivados",
        "demandas_avulsas":       "Demandas Avulsas",
        "atendimentos":           "Atendimentos Realizados",
    }
    CAMPO_DATA = {
        "processos_ativos":       "data_entrada",
        "processos_aguardando":   "data_entrada",
        "processos_protocolados": "data_entrada",
        "processos_arquivados":   "data_entrada",
        "demandas_avulsas":       "data_solicitacao",
        "atendimentos":           "data_atendimento",
    }
    if   tipo == "processos_ativos":       dados = listar_processos(["Em Andamento","Aguardando Documentos"])
    elif tipo == "processos_aguardando":   dados = listar_processos("Aguardando Documentos")
    elif tipo == "processos_protocolados": dados = listar_processos("Protocolado")
    elif tipo == "processos_arquivados":   dados = listar_processos("Arquivado")
    elif tipo == "demandas_avulsas":       dados = listar_demandas()
    else:                                  dados = listar_atendimentos()
    if assessor_filtro:
        dados = [d for d in dados if (d.get("assessor") or "") == assessor_filtro]
    campo = CAMPO_DATA.get(tipo, "data_entrada")
    if data_ini:
        dados = [d for d in dados if (d.get(campo) or "") >= data_ini.isoformat()]
    if data_fim:
        dados = [d for d in dados if (d.get(campo) or "") <= data_fim.isoformat()]
    return dados, labels.get(tipo, "Relatório")

# ══════════════════════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
#  NOTIFICAÇÕES — Atendimentos sem resolução após 24h
# ══════════════════════════════════════════════════════════════════════════════
def verificar_notificacoes() -> list[dict]:
    """Retorna atendimentos com resolução vazia criados há mais de 24h."""
    todos = listar_atendimentos()
    limite = datetime.datetime.now() - datetime.timedelta(hours=24)
    pendentes = []
    for a in todos:
        if a.get("resolucao","").strip():
            continue  # já tem resolução
        # Tenta parsear data do atendimento + hora de criação
        try:
            criado_em = a.get("criado_em","")
            if criado_em:
                dt = datetime.datetime.strptime(criado_em, "%d/%m/%Y %H:%M")
            else:
                # Fallback: usa a data do atendimento como meia-noite
                dt = datetime.datetime.fromisoformat(a["data_atendimento"])
            if dt <= limite:
                pendentes.append(a)
        except Exception:
            pass
    return pendentes

def exibir_notificacoes():
    """Exibe banner de notificação se houver atendimentos pendentes."""
    perfil = st.session_state.get("perfil","")
    if perfil != "assessor":
        return
    pendentes = verificar_notificacoes()
    if not pendentes:
        return
    nomes = ", ".join(
        f"#{a['id']} {a.get('nome_pessoa','?').split()[0]}"
        for a in pendentes[:5]
    )
    extra = f" e mais {len(pendentes)-5}" if len(pendentes) > 5 else ""
    st.warning(
        f"🔔 **{len(pendentes)} atendimento(s) sem resolução há mais de 24h:** "
        f"{nomes}{extra}. Acesse o módulo de Atendimentos e registre a solução.",
        icon="⚠️"
    )

def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* ── Força fundo branco (neutraliza modo escuro do browser) ── */
    html, body, .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stMain"], .main, .block-container {
        background-color: #f0f4f8 !important;
        color: #1e293b !important;
    }
    /* Garante que textos fora de componentes fiquem escuros */
    p, span, label, div, h1, h2, h3, h4, h5, h6 { color: #1e293b; }

    /* Oculta elementos padrão do Streamlit */
    #MainMenu, footer { visibility: hidden; }

    /* ── SIDEBAR: força sempre aberta, esconde botão de recolher ── */
    /* Esconde o botão "»" de colapsar */
    [data-testid="collapsedControl"],
    button[kind="header"],
    .st-emotion-cache-dvne4q,
    [class*="collapsedControl"] { display: none !important; }

    /* Força a sidebar a estar sempre expandida */
    [data-testid="stSidebar"][aria-expanded="false"] {
        transform: none !important;
        visibility: visible !important;
        margin-left: 0 !important;
        left: 0 !important;
    }
    section[data-testid="stSidebar"] {
        min-width: 272px !important;
        width: 272px !important;
        transform: none !important;
        visibility: visible !important;
        position: relative !important;
    }
    section[data-testid="stSidebar"] > div { padding-top: 0 !important; }

    /* Sidebar – cor e tipografia */
    section[data-testid="stSidebar"] {
        background: #0f2167 !important;
        border-right: 3px solid #c9a227 !important;
    }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label { color: #dce6f5 !important; }

    /* Botão sair */
    section[data-testid="stSidebar"] .stButton > button {
        background: rgba(201,162,39,0.15) !important;
        color: #c9a227 !important;
        border: 1px solid #c9a227 !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        transition: all .2s;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: #c9a227 !important;
        color: #0f2167 !important;
    }

    /* Métricas sidebar */
    section[data-testid="stSidebar"] [data-testid="stMetric"] {
        background: rgba(255,255,255,0.06) !important;
        border-radius: 8px !important;
        padding: 8px 12px !important;
        margin-bottom: 5px !important;
    }
    section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
        color: #c9a227 !important; font-size: 22px !important;
    }
    section[data-testid="stSidebar"] [data-testid="stMetricLabel"] {
        font-size: 11px !important; opacity: .8;
    }

    /* ── Área principal ── */
    .main .block-container { padding: 16px 28px 32px 28px !important; max-width: 100% !important; }

    /* Containers e cards do Streamlit – fundo branco forçado */
    [data-testid="stVerticalBlock"] > [data-testid="element-container"] > div > div,
    div[data-testid="stHorizontalBlock"],
    div.stContainer,
    [data-testid="stMetric"],
    div[class*="stAlert"],
    div[data-testid="stExpander"] { color: #1e293b !important; }

    /* Força fundo branco em todos os st.container(border=True) */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: white !important;
        border-color: #e2e8f0 !important;
    }

    /* ── Inputs, selects, textareas — força light mode no Cloud ── */
    input, textarea, select,
    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox > div > div,
    .stSelectbox [data-baseweb="select"] > div,
    .stDateInput input,
    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea,
    [data-baseweb="select"] div {
        background: #ffffff !important;
        background-color: #ffffff !important;
        color: #1e293b !important;
        border-color: #cbd5e1 !important;
    }

    /* Dropdown aberto */
    [data-baseweb="popover"] li,
    [data-baseweb="menu"] li,
    [role="option"],
    [role="listbox"] { background: white !important; color: #1e293b !important; }
    [role="option"]:hover { background: #f0f4f8 !important; }

    /* Labels de todos os inputs */
    .stTextInput label, .stTextArea label, .stSelectbox label,
    .stDateInput label, .stRadio label, .stCheckbox label,
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] { color: #374151 !important; }

    /* Botões secundários (não-primary) */
    .stButton > button:not([kind="primary"]) {
        background: #ffffff !important;
        color: #1e293b !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 6px !important;
    }
    .stButton > button:not([kind="primary"]):hover {
        background: #f0f4f8 !important;
        border-color: #1e3a8a !important;
        color: #1e3a8a !important;
    }

    /* Expanders */
    details, summary,
    [data-testid="stExpander"],
    [data-testid="stExpander"] > div {
        background: white !important;
        color: #1e293b !important;
        border-color: #e2e8f0 !important;
    }
    summary:hover { background: #f8fafc !important; }

    /* Captions */
    .stCaption, [data-testid="stCaptionContainer"] p { color: #64748b !important; }

    /* Info / success / warning / error alerts */
    [data-testid="stAlert"] { color: inherit !important; }
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] span { color: inherit !important; }

    /* Número dos inputs de data */
    input[type="number"] { background: white !important; color: #1e293b !important; }

    /* Download button */
    .stDownloadButton > button {
        background: #1e3a8a !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
    }
    .stDownloadButton > button:hover { background: #1e40af !important; }

    /* ── Header ── */
    .naj-header {
        background: linear-gradient(135deg,#0f2167 0%,#1a3490 60%,#1e4db0 100%);
        border-radius: 10px; margin-bottom: 20px;
        display: flex; align-items: stretch; overflow: hidden;
        box-shadow: 0 4px 18px rgba(15,33,103,.28);
        border-bottom: 3px solid #c9a227;
    }
    .naj-header-logo {
        background: rgba(0,0,0,.18); padding: 10px 18px;
        display: flex; align-items: center;
        border-right: 1px solid rgba(255,255,255,.1);
    }
    .naj-header-logo img { height: 64px; }
    .naj-header-body { flex:1; padding: 14px 22px; display:flex; flex-direction:column; justify-content:center; }
    .naj-header-body h1 { margin:0 0 2px; font-size:18px; font-weight:700; color:white; letter-spacing:.3px; }
    .naj-header-body p  { margin:0; font-size:12px; color:rgba(255,255,255,.7); }
    .naj-header-info    { padding:14px 22px; text-align:right; border-left:1px solid rgba(255,255,255,.1);
                          display:flex; flex-direction:column; justify-content:center; }
    .naj-header-info .usr { font-size:13px; color:#c9a227; font-weight:700; }
    .naj-header-info .dt  { font-size:11px; color:rgba(255,255,255,.55); margin-top:3px; }

    /* ── Títulos de seção ── */
    .sec-title {
        font-size:15px; font-weight:700; color:#1e3a8a;
        padding-bottom:8px; border-bottom:2px solid #dbeafe;
        margin-bottom:16px; display:flex; align-items:center; gap:8px;
    }

    /* ── Métricas do dashboard ── */
    .mcard {
        background:white; border-radius:10px; padding:16px 20px;
        border-left:4px solid #1e3a8a;
        box-shadow:0 2px 8px rgba(0,0,0,.07); margin-bottom:4px;
    }
    .mcard.verm  { border-left-color:#b91c1c; }
    .mcard.amar  { border-left-color:#ca8a04; }
    .mcard.verd  { border-left-color:#15803d; }
    .mcard.azul  { border-left-color:#1e3a8a; }
    .mnum   { font-size:30px; font-weight:700; color:#1e3a8a; line-height:1; }
    .mlabel { font-size:12px; color:#64748b; margin-top:4px; }

    /* ── Badges ── */
    .badge { display:inline-block; padding:2px 10px; border-radius:9999px;
             font-size:11px; font-weight:600; letter-spacing:.3px; }
    .b-and  { background:#dbeafe; color:#1e40af; }
    .b-ag   { background:#fef3c7; color:#854d0e; }
    .b-prot { background:#e0f2fe; color:#0369a1; }
    .b-arq  { background:#f1f5f9; color:#475569; }
    .b-pend { background:#fefce8; color:#854d0e; }
    .b-conc { background:#ecfdf5; color:#15803d; }
    .b-alta { background:#fee2e2; color:#b91c1c; }
    .b-med  { background:#fefce8; color:#854d0e; }
    .b-bax  { background:#ecfdf5; color:#15803d; }

    /* ── Indicador de dias ── */
    .du  { color:#b91c1c; font-weight:700; font-size:13px; }
    .da  { color:#ca8a04; font-weight:700; font-size:13px; }
    .dok { color:#15803d; font-weight:700; font-size:13px; }

    /* ── Botões primários ── */
    .stButton > button[kind="primary"] { background:#1e3a8a !important; font-weight:600 !important; }
    .stButton > button[kind="primary"]:hover { background:#1e40af !important; }

    /* ── Divisores entre linhas ── */
    .row-div { border:none; border-top:1px solid #f1f5f9; margin:4px 0; }

    /* ══════════════════════════════════════════
       BOTÕES — fonte branca em TODOS os botões
       da área principal (cadastrar, download, etc.)
       Abordagem máxima: cobre todas as versões do Streamlit
    ══════════════════════════════════════════ */

    /* Qualquer botão fora da sidebar */
    .main .stButton button,
    .main button,
    [data-testid="stMain"] button,
    [data-testid="stMain"] .stButton button {
        background-color: rgba(201,162,39,0.15) !important;
        color: #c9a227 !important;
        border: 1px solid #c9a227 !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
    }
    .main .stButton button:hover,
    [data-testid="stMain"] button:hover {
        background-color: #1e40af !important;
        color: #ffffff !important;
    }

    /* Download — garante fundo azul e texto branco */
    .stDownloadButton button,
    [data-testid="stDownloadButton"] button,
    .main .stDownloadButton button {
        background-color: rgba(201,162,39,0.15) !important;
        color: #c9a227 !important;
        border: 1px solid #c9a227 !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
    }
    .stDownloadButton button:hover { background-color: #1e40af !important; }

    /* Botões de ação pequenos (✏️ ⏳ 📨 🗑️) — fundo suave */
    .main .stButton button[title="Editar"],
    .main .stButton button[title="Excluir"],
    .main .stButton button[title="Aguardando Docs"],
    .main .stButton button[title="Protocolar"] {
        background-color: #e2e8f0 !important;
        color: #1e293b !important;
        border: 1px solid #cbd5e1 !important;
    }

    /* Botão Cancelar / Cancelar ação — cinza claro */
    .main .stButton button[kind="secondary"] {
        background-color: #f1f5f9 !important;
        color: #475569 !important;
        border: 1px solid #cbd5e1 !important;
    }

    /* Garante que botão da sidebar não seja afetado */
    section[data-testid="stSidebar"] .stButton button {
        background: rgba(201,162,39,0.15) !important;
        color: #c9a227 !important;
        border: 1px solid #c9a227 !important;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        background: #c9a227 !important;
        color: #0f2167 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS VISUAIS
# ══════════════════════════════════════════════════════════════════════════════
STATUS_BADGE = {
    "Em Andamento":          "b-and",
    "Aguardando Documentos": "b-ag",
    "Protocolado":           "b-prot",
    "Arquivado":             "b-arq",
    "Pendente":              "b-pend",
    "Concluída":             "b-conc",
}
PRIO_BADGE = {"Alta": "b-alta", "Média": "b-med", "Baixa": "b-bax"}

def badge(txt: str, cls: str) -> str:
    return f'<span class="badge {cls}">{txt}</span>'

def dias_html(n: int) -> str:
    if n >= 30: return f'<span class="du">⚠ {n}d</span>'
    if n >= 15: return f'<span class="da">⏱ {n}d</span>'
    return f'<span class="dok">✓ {n}d</span>'

def section_title(icon: str, txt: str):
    st.markdown(f'<div class="sec-title">{icon}&nbsp;{txt}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  TELA DE LOGIN
# ══════════════════════════════════════════════════════════════════════════════
def tela_login():
    # CSS específico da tela de login — força fundo azul E esconde sidebar
    logo_b64 = _get_logo_b64()
    logo_tag = (f'<img src="data:image/jpeg;base64,{logo_b64}" style="height:72px;'
                f'border-radius:8px;margin-bottom:16px;display:block;margin-left:auto;margin-right:auto;">'
                if logo_b64 else '<div style="font-size:52px;text-align:center;margin-bottom:12px;">⚖️</div>')

    st.markdown(f"""
    <style>
    /* Remove tudo do Streamlit e pinta a tela de azul */
    #MainMenu, footer, header {{ visibility: hidden !important; }}
    section[data-testid="stSidebar"] {{ display: none !important; }}
    [data-testid="collapsedControl"] {{ display: none !important; }}

    html, body {{
        background-color: #0f2167 !important;
        color: white !important;
        font-family: 'Inter', 'Segoe UI', sans-serif !important;
    }}
    .stApp {{
        background: linear-gradient(145deg, #0a1744 0%, #1a3490 50%, #1e4db0 100%) !important;
    }}
    [data-testid="stAppViewContainer"] {{
        background: linear-gradient(145deg, #0a1744 0%, #1a3490 50%, #1e4db0 100%) !important;
    }}
    [data-testid="stMain"] {{
        background: transparent !important;
    }}
    .main {{
        background: transparent !important;
    }}
    .block-container {{
        background: transparent !important;
        padding-top: 60px !important;
        max-width: 440px !important;
        margin: 0 auto !important;
    }}
    /* Esconde o botão padrão de collapse da sidebar no estado de login */
    button[data-testid="baseButton-header"] {{ display:none !important; }}

    /* Texto branco em toda a página de login */
    .block-container p,
    .block-container span,
    .block-container label,
    .block-container h1,
    .block-container h2,
    .block-container h3,
    .block-container h4 {{
        color: white !important;
    }}
    /* Inputs com fundo semi-transparente */
    .block-container .stTextInput input {{
        background: rgba(255,255,255,0.12) !important;
        color: white !important;
        border: 1px solid rgba(255,255,255,0.3) !important;
        border-radius: 8px !important;
    }}
    .block-container .stTextInput input::placeholder {{
        color: rgba(255,255,255,0.45) !important;
    }}
    .block-container .stTextInput input:focus {{
        background: rgba(255,255,255,0.18) !important;
        border-color: #c9a227 !important;
        box-shadow: 0 0 0 2px rgba(201,162,39,0.3) !important;
    }}
    /* Labels dos inputs — brancos e visíveis */
    .block-container label,
    .block-container [data-testid="stWidgetLabel"] p,
    .block-container [data-testid="stTextInput"] label {{
        color: rgba(255,255,255,0.95) !important;
        font-size: 14px !important;
        font-weight: 600 !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.3) !important;
    }}
    /* Inputs brancos e bem visíveis */
    .block-container input,
    .block-container .stTextInput input,
    .block-container [data-baseweb="input"] input {{
        background: #ffffff !important;
        background-color: #ffffff !important;
        color: #1e293b !important;
        border: 2px solid rgba(255,255,255,0.4) !important;
        border-radius: 8px !important;
        font-size: 15px !important;
        padding: 10px 14px !important;
    }}
    .block-container input:focus,
    .block-container .stTextInput input:focus {{
        border-color: #c9a227 !important;
        box-shadow: 0 0 0 3px rgba(201,162,39,0.35) !important;
    }}
    .block-container input::placeholder {{ color: #94a3b8 !important; }}
    /* Botão entrar — dourado e bem visível */
    .block-container .stButton > button,
    .block-container button[data-testid="baseButton-primary"],
    .block-container [data-testid="stBaseButton-primary"] {{
        background: #c9a227 !important;
        background-color: #c9a227 !important;
        color: #0a1744 !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        font-size: 15px !important;
        padding: 12px !important;
        width: 100% !important;
        transition: all 0.2s !important;
    }}
    .block-container .stButton > button:hover {{
        background: #e4b82d !important;
        background-color: #e4b82d !important;
        transform: translateY(-1px) !important;
    }}
    /* Ícone de olho do password */
    .block-container [data-testid="stTextInput"] svg {{ fill: rgba(100,116,139,0.8) !important; }}
    /* Mensagem de erro */
    .block-container [data-testid="stAlert"] {{
        background: rgba(185,28,28,0.25) !important;
        border: 1px solid rgba(248,113,113,0.5) !important;
        border-radius: 8px !important;
    }}
    .block-container [data-testid="stAlert"] p {{ color: #fca5a5 !important; }}
    </style>

    <div style="text-align:center; margin-bottom:8px;">
        {logo_tag}
        <div style="font-size:20px;font-weight:700;color:white;margin-bottom:4px;">
            Núcleo de Assistência Jurídica
        </div>
        <div style="font-size:13px;color:rgba(255,255,255,0.6);">
            Prefeitura Municipal de Iúna/ES
        </div>
    </div>

    <div style="background:rgba(255,255,255,0.13);border:1px solid rgba(255,255,255,0.25);
                border-radius:14px;padding:28px 28px 8px;margin-top:20px;">
        <div style="font-size:18px;font-weight:700;color:white;margin-bottom:4px;
                    display:flex;align-items:center;gap:8px;">
            🔐 Acesso ao Sistema
        </div>
        <p style="color:rgba(255,255,255,0.7);font-size:13px;margin-bottom:16px;">
            Digite seu usuário e senha para entrar
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Inputs e botão dentro do Streamlit (funcional)
    # O CSS acima estiliza eles para combinar com o card azul
    login = st.text_input("Usuário", placeholder="portaria / kleber / gustavo / erikson", key="li_u")
    senha = st.text_input("Senha", type="password", key="li_p")

    if st.button("Entrar no Sistema →", use_container_width=True, key="li_btn"):
        user = USERS.get((login or "").strip().lower())
        if user and user["senha_hash"] == _hash(senha):
            st.session_state.update({
                "logado":       True,
                "login":        login.strip().lower(),
                "nome_usuario": user["nome"],
                "perfil":       user["perfil"],
            })
            st.rerun()
        else:
            st.error("⚠️ Usuário ou senha incorretos. Tente novamente.")

    st.markdown("""
    <div style="text-align:center;color:rgba(255,255,255,0.25);font-size:11px;margin-top:24px;">
        v3.0 &nbsp;•&nbsp; Python + Streamlit &nbsp;•&nbsp; SQLite
    </div>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════════════════════
def render_header():
    logo_b64 = _get_logo_b64()
    hoje_fmt  = datetime.date.today().strftime("%d/%m/%Y")
    dia_map   = {"Monday":"Segunda","Tuesday":"Terça","Wednesday":"Quarta",
                 "Thursday":"Quinta","Friday":"Sexta","Saturday":"Sábado","Sunday":"Domingo"}
    dia       = dia_map.get(datetime.date.today().strftime("%A"), "")
    nome      = st.session_state.get("nome_usuario","")
    perfil    = st.session_state.get("perfil","")
    perfil_lb = "Assessor Jurídico" if perfil == "assessor" else "Portaria"

    logo_html = (f'<div class="naj-header-logo">'
                 f'<img src="data:image/jpeg;base64,{logo_b64}" /></div>'
                 if logo_b64 else "")

    st.markdown(f"""
    <div class="naj-header">
        {logo_html}
        <div class="naj-header-body">
            <h1>Sistema de Controle de Processos</h1>
            <p>Núcleo de Assistência Jurídica à População de Baixa Renda &nbsp;·&nbsp; Prefeitura Municipal de Iúna/ES</p>
        </div>
        <div class="naj-header-info">
            <div class="usr">👤 {nome.split()[0]}&nbsp;<span style="font-weight:400;font-size:11px;
                color:rgba(255,255,255,.5);">({perfil_lb})</span></div>
            <div class="dt">{dia}, {hoje_fmt}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
def render_sidebar() -> str:
    perfil = st.session_state["perfil"]
    nome   = st.session_state["nome_usuario"]

    with st.sidebar:
        st.markdown(f"""
        <div style="background:rgba(0,0,0,.22);border-radius:8px;padding:12px 14px;margin:12px 0 4px;">
            <div style="font-size:10px;color:rgba(255,255,255,.4);text-transform:uppercase;letter-spacing:1.2px;">
                {'⚖️ Assessor' if perfil=='assessor' else '🏢 Portaria'}
            </div>
            <div style="font-size:15px;color:#c9a227;font-weight:700;margin-top:3px;">{nome.split()[0]}</div>
            <div style="font-size:11px;color:rgba(255,255,255,.45);margin-top:1px;">{nome}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr style="border-color:rgba(255,255,255,.1);margin:8px 0;">', unsafe_allow_html=True)

        if perfil == "assessor":
            st.markdown('<div style="font-size:10px;color:rgba(255,255,255,.35);text-transform:uppercase;'
                        'letter-spacing:1.2px;padding:0 4px;margin-bottom:4px;">Módulos</div>',
                        unsafe_allow_html=True)
            menu = st.radio("nav", [
                "📊  Dashboard",
                "📌  Processos Ativos",
                "📨  Processos Protocolados",
                "📁  Arquivados",
                "📋  Demandas Avulsas",
                "🧑‍💼  Atendimentos",
                "📄  Relatórios PDF",
            ], label_visibility="collapsed")
        else:
            st.markdown('<div style="font-size:10px;color:rgba(255,255,255,.35);text-transform:uppercase;'
                        'letter-spacing:1.2px;padding:0 4px;margin-bottom:4px;">Módulos</div>',
                        unsafe_allow_html=True)
            menu = st.radio("nav", [
                "📌  Processos Ativos",
                "📋  Demandas Avulsas",
                "🧑‍💼  Atendimentos",
            ], label_visibility="collapsed")
            st.markdown("""
            <div style="background:rgba(201,162,39,.1);border:1px solid rgba(201,162,39,.3);
                        border-radius:8px;padding:8px 12px;font-size:11px;color:rgba(255,255,255,.55);margin-top:6px;">
                <b style="color:#c9a227;">Perfil: Portaria</b><br>
                Pode cadastrar processos, demandas e atendimentos.
            </div>""", unsafe_allow_html=True)

        st.markdown('<hr style="border-color:rgba(255,255,255,.1);margin:8px 0;">', unsafe_allow_html=True)

        # Métricas
        st.markdown('<div style="font-size:10px;color:rgba(255,255,255,.35);text-transform:uppercase;'
                    'letter-spacing:1.2px;padding:0 4px;margin-bottom:4px;">Situação Atual</div>',
                    unsafe_allow_html=True)
        ativos  = listar_processos(["Em Andamento","Aguardando Documentos"])
        prot    = listar_processos("Protocolado")
        pend    = listar_demandas("Pendente")
        at_hoje = [a for a in listar_atendimentos() if a.get("data_atendimento","") == hoje_iso()]

        st.metric("📌 Processos Ativos",   len(ativos))
        st.metric("📨 Protocolados",        len(prot))
        st.metric("📋 Demandas Pendentes",  len(pend))
        st.metric("🧑‍💼 Atendimentos Hoje",  len(at_hoje))

        st.markdown('<hr style="border-color:rgba(255,255,255,.1);margin:8px 0;">', unsafe_allow_html=True)
        if st.button("🚪  Sair do Sistema", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    return menu.strip()

# ══════════════════════════════════════════════════════════════════════════════
#  FORMULÁRIO DE PROCESSO (helper reutilizável)
# ══════════════════════════════════════════════════════════════════════════════
def form_processo(key: str, permite_status: bool = False):
    usuario = st.session_state["nome_usuario"]
    fp      = st.session_state[key]
    label   = "✏️ Editar Processo" if fp["id"] else "➕ Cadastrar Novo Processo"

    with st.expander(label, expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            dv    = datetime.date.fromisoformat(fp["data_entrada"]) if fp.get("data_entrada") else datetime.date.today()
            dent  = st.date_input("📅 Data de Entrada", value=dv, key=f"{key}_d")
            pasta = st.text_input("📁 Número da Pasta", value=fp.get("numero_pasta",""),
                                  key=f"{key}_p", placeholder="Ex: 2026/045")
        with c2:
            nome   = st.text_input("👤 Nome do Assistido *", value=fp.get("nome_assistido",""), key=f"{key}_n")
            optsA  = ["(Não atribuído)"] + ASSESSORES
            idxA   = optsA.index(fp["assessor"]) if fp.get("assessor") in optsA else 0
            assess = st.selectbox("👨‍⚖️ Assessor Responsável", optsA, index=idxA, key=f"{key}_a")
        with c3:
            idxP  = PRIORIDADES.index(fp["prioridade"]) if fp.get("prioridade") in PRIORIDADES else 1
            prio  = st.selectbox("🎯 Prioridade", PRIORIDADES, index=idxP, key=f"{key}_pr")
            if permite_status and fp["id"]:
                idxS   = STATUS_PROCESSO.index(fp["status"]) if fp.get("status") in STATUS_PROCESSO else 0
                status = st.selectbox("📊 Status", STATUS_PROCESSO, index=idxS, key=f"{key}_st")
            else:
                status = fp.get("status","Em Andamento")
        desc = st.text_area("📝 Descrição do Processo", value=fp.get("descricao",""),
                            key=f"{key}_desc", height=75)

        b1, b2, _ = st.columns([1, 1, 5])
        with b1:
            if st.button("💾 Salvar", type="primary", key=f"{key}_save"):
                if not nome.strip():
                    st.error("O nome do assistido é obrigatório.")
                else:
                    av = assess if assess != "(Não atribuído)" else ""
                    if fp["id"]:
                        atualizar_processo(fp["id"], dent.isoformat(), pasta, nome, desc, av, prio, status, usuario)
                        st.success("✅ Processo atualizado com sucesso!")
                    else:
                        inserir_processo(dent.isoformat(), pasta, nome, desc, av, prio, usuario)
                        st.success("✅ Processo cadastrado com sucesso!")
                    del st.session_state[key]
                    st.rerun()
        with b2:
            if st.button("❌ Cancelar", key=f"{key}_cancel"):
                del st.session_state[key]
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  CARD DE PROCESSO (helper reutilizável)
# ══════════════════════════════════════════════════════════════════════════════
def card_processo(p: dict, form_key: str, acoes_status: bool = False):
    usuario  = st.session_state["nome_usuario"]
    dias     = dias_aberto(p.get("data_entrada",""))
    st_cls   = STATUS_BADGE.get(p["status"],"")
    pr_cls   = PRIO_BADGE.get(p.get("prioridade","Média"),"")
    ass_nome = (p.get("assessor","") or "Não atribuído").split()[0]
    pasta    = p.get("numero_pasta","") or "—"

    c_id, c_info, c_badges, c_dias, c_acoes = st.columns([0.6, 3.6, 2.2, 1.1, 1.7])

    with c_id:
        st.markdown(f"**#{p['id']}**")
        st.caption(pasta)

    with c_info:
        st.markdown(f"**{p['nome_assistido']}**")
        desc = (p.get("descricao","") or "").strip()
        if desc: st.caption(desc[:95] + ("…" if len(desc) > 95 else ""))
        st.caption(f"📅 Entrada: {fmt_data(p.get('data_entrada',''))}")

    with c_badges:
        st.markdown(
            badge(p["status"], st_cls) + "&nbsp;&nbsp;" + badge(p.get("prioridade","—"), pr_cls) +
            f'<br><span style="font-size:11px;color:#64748b;">👨‍⚖️ {ass_nome}</span>',
            unsafe_allow_html=True
        )

    with c_dias:
        st.markdown(dias_html(dias), unsafe_allow_html=True)

    with c_acoes:
        _perfil = st.session_state.get("perfil","assessor")
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if _perfil == "assessor":
                if st.button("✏️", key=f"ed_{form_key}_{p['id']}", help="Editar"):
                    st.session_state[form_key] = {
                        "id": p["id"], "data_entrada": p.get("data_entrada", hoje_iso()),
                        "numero_pasta": p.get("numero_pasta",""),
                        "nome_assistido": p["nome_assistido"], "descricao": p.get("descricao",""),
                        "assessor": p.get("assessor",""), "prioridade": p.get("prioridade","Média"),
                        "status": p.get("status","Em Andamento"),
                    }
                    st.rerun()
        if acoes_status and _perfil == "assessor":
            with b2:
                if st.button("⏳", key=f"ag_{form_key}_{p['id']}", help="Aguardando Docs"):
                    alterar_status_processo(p["id"], "Aguardando Documentos", usuario); st.rerun()
            with b3:
                if st.button("📨", key=f"pr_{form_key}_{p['id']}", help="Protocolar"):
                    alterar_status_processo(p["id"], "Protocolado", usuario); st.rerun()
        with b4:
            if _perfil == "assessor":
                if st.button("🗑️", key=f"dl_{form_key}_{p['id']}", help="Excluir"):
                    st.session_state[f"_dp_{p['id']}"] = True; st.rerun()

    if st.session_state.get(f"_dp_{p['id']}"):
        st.warning(f"⚠️ Confirma exclusão do processo **#{p['id']} – {p['nome_assistido']}**?")
        cc1, cc2, _ = st.columns([1, 1, 5])
        with cc1:
            if st.button("✅ Confirmar", key=f"cdp_{p['id']}", type="primary"):
                deletar_processo(p["id"])
                del st.session_state[f"_dp_{p['id']}"]
                st.rerun()
        with cc2:
            if st.button("❌ Cancelar", key=f"cdpc_{p['id']}"):
                del st.session_state[f"_dp_{p['id']}"]
                st.rerun()

    st.markdown('<hr class="row-div">', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  PESQUISA
# ══════════════════════════════════════════════════════════════════════════════
def filtrar_processos(dados: list, termo: str) -> list:
    if not termo.strip(): return dados
    t = termo.strip().lower()
    return [p for p in dados if
            t in p.get("nome_assistido","").lower()
            or t in (p.get("numero_pasta","") or "").lower()
            or t in str(p.get("id",""))
            or t in (p.get("descricao","") or "").lower()
            or t in (p.get("assessor","") or "").lower()]

# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
def modulo_dashboard():
    section_title("📊", "Dashboard — Prioridades e Situação Geral")

    ativos   = listar_processos(["Em Andamento","Aguardando Documentos"])
    prot     = listar_processos("Protocolado")
    arq      = listar_processos("Arquivado")
    pend     = listar_demandas("Pendente")
    at_hoje  = [a for a in listar_atendimentos() if a.get("data_atendimento","") == hoje_iso()]
    criticos = [p for p in ativos if dias_aberto(p.get("data_entrada","")) >= 30]

    # Métricas
    c1,c2,c3,c4,c5 = st.columns(5)
    def met(col, n, label, cor="azul"):
        with col:
            st.markdown(
                f'<div class="mcard {cor}"><div class="mnum">{n}</div>'
                f'<div class="mlabel">{label}</div></div>',
                unsafe_allow_html=True
            )
    met(c1, len(ativos),   "📌 Processos Ativos",   "verm" if criticos else "azul")
    met(c2, len(prot),     "📨 Protocolados",         "azul")
    met(c3, len(arq),      "📁 Arquivados",            "verd")
    met(c4, len(pend),     "📋 Demandas Pendentes",    "amar" if pend else "verd")
    met(c5, len(at_hoje),  "🧑‍💼 Atendimentos Hoje",   "verd")

    if criticos:
        st.error(f"⚠️ **{len(criticos)} processo(s) com mais de 30 dias em aberto** — atenção imediata: "
                 + ", ".join(f"#{p['id']} {p['nome_assistido'].split()[0]}" for p in criticos[:6]))

    # Notificações de atendimentos sem resolução
    at_sem_res = verificar_notificacoes()
    if at_sem_res:
        nomes_at = ", ".join(f"#{a['id']} {a.get('nome_pessoa','?').split()[0]}" for a in at_sem_res[:5])
        extra_at = f" e mais {len(at_sem_res)-5}" if len(at_sem_res) > 5 else ""
        st.warning(f"🔔 **{len(at_sem_res)} atendimento(s) sem resolução há mais de 24h:** "
                   f"{nomes_at}{extra_at}. Registre a resolução no módulo de Atendimentos.")

    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_r = st.columns([1.6, 1])

    # Processos ativos – mais antigos primeiro
    with col_l:
        st.markdown('<div class="sec-title" style="font-size:13px;">📌 Processos Ativos — Mais Antigos Primeiro &nbsp;'
                    '<span style="font-size:11px;font-weight:400;color:#64748b;">'
                    '⚠ ≥30d = urgente &nbsp;|&nbsp; ⏱ 15-30d = atenção &nbsp;|&nbsp; ✓ &lt;15d = ok</span></div>',
                    unsafe_allow_html=True)
        if not ativos:
            st.success("✅ Nenhum processo ativo.")
        else:
            h1,h2,h3,h4,h5 = st.columns([0.6,3.6,2.2,1.1,1.7])
            for c, t in zip([h1,h2,h3,h4,h5],["ID/Pasta","Assistido / Descrição","Status / Assessor","Em aberto","Ações"]):
                c.markdown(f'<span style="font-size:11px;color:#94a3b8;font-weight:600;">{t}</span>', unsafe_allow_html=True)
            st.markdown('<hr style="margin:4px 0;border:none;border-top:2px solid #dbeafe;">', unsafe_allow_html=True)
            for p in ativos:
                card_processo(p, "dash_proc", acoes_status=True)

        if "dash_proc" in st.session_state:
            form_processo("dash_proc", permite_status=True)

    # Demandas pendentes – mais antigas primeiro
    with col_r:
        st.markdown('<div class="sec-title" style="font-size:13px;">📋 Demandas Pendentes — Mais Antigas Primeiro</div>',
                    unsafe_allow_html=True)
        if not pend:
            st.success("✅ Nenhuma demanda pendente!")
        else:
            for d in pend:
                dias = dias_aberto(d.get("data_solicitacao",""))
                ass  = (d.get("assessor","") or "—").split()[0]
                with st.container(border=True):
                    st.markdown(
                        f"**#{d['id']}** &nbsp;·&nbsp; {d['nome_assistido']}<br>"
                        f'<span style="font-size:11px;color:#64748b;">'
                        f"📁 {d.get('numero_pasta','—') or '—'} &nbsp;|&nbsp; 👨‍⚖️ {ass}</span>",
                        unsafe_allow_html=True
                    )
                    dem = (d.get("demanda","") or "")[:65]
                    if dem: st.caption(dem)
                    ca, cb = st.columns(2)
                    with ca: st.markdown(dias_html(dias), unsafe_allow_html=True)
                    with cb: st.caption(fmt_data(d.get("data_solicitacao","")))

# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO: LISTA DE PROCESSOS
# ══════════════════════════════════════════════════════════════════════════════
def modulo_processos(modo: str):
    CFG = {
        "ativos":       ("📌","Processos Ativos",       ["Em Andamento","Aguardando Documentos"]),
        "protocolados": ("📨","Processos Protocolados", "Protocolado"),
        "arquivados":   ("📁","Procedimentos Arquivados","Arquivado"),
    }
    icon, titulo, filtro = CFG[modo]
    form_key = f"fp_{modo}"
    section_title(icon, titulo)

    if modo == "ativos":
        if st.button("➕ Cadastrar Novo Processo", type="primary", key=f"btn_novo_{modo}"):
            st.session_state[form_key] = {
                "id": None, "data_entrada": hoje_iso(), "numero_pasta": "",
                "nome_assistido": "", "descricao": "", "telefone":"", "assessor": "",
                "prioridade": "Média", "status": "Em Andamento",
            }

    if form_key in st.session_state:
        form_processo(form_key, permite_status=(modo != "ativos"))

    # Pesquisa + filtro de assessor
    fc1, fc2 = st.columns([2.5, 1])
    with fc1:
        termo = st.text_input("🔍 Pesquisar",
                              placeholder="Nome do assistido, número da pasta, ID ou assessor...",
                              key=f"srch_{modo}")
    with fc2:
        opts_f = ["Todos os assessores"] + [a.split()[0] for a in ASSESSORES]
        filtro_a = st.selectbox("Assessor", opts_f, key=f"fa_{modo}")

    dados_brutos = listar_processos(filtro)
    dados        = filtrar_processos(dados_brutos, termo)
    if filtro_a != "Todos os assessores":
        dados = [p for p in dados if (p.get("assessor","") or "").startswith(filtro_a)]

    if not dados:
        msg = "Nenhum resultado para a pesquisa." if (termo or filtro_a != "Todos os assessores") else "Nenhum registro nesta categoria."
        st.info(f"📪 {msg}")
        return

    st.caption(f"**{len(dados)}** de **{len(dados_brutos)}** registro(s) · ordenados por data de entrada (mais antigo primeiro)")

    h1,h2,h3,h4,h5 = st.columns([0.6,3.6,2.2,1.1,1.7])
    for c, t in zip([h1,h2,h3,h4,h5],["ID/Pasta","Assistido / Descrição","Status / Assessor","Em aberto","Ações"]):
        c.markdown(f'<span style="font-size:11px;color:#94a3b8;font-weight:600;">{t}</span>', unsafe_allow_html=True)
    st.markdown('<hr style="margin:4px 0;border:none;border-top:2px solid #dbeafe;">', unsafe_allow_html=True)

    for p in dados:
        card_processo(p, form_key, acoes_status=(modo == "ativos"))

# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO: DEMANDAS AVULSAS
# ══════════════════════════════════════════════════════════════════════════════
def modulo_demandas():
    usuario = st.session_state["nome_usuario"]
    section_title("📋","Demandas Avulsas")

    if st.button("➕ Nova Demanda Avulsa", type="primary"):
        st.session_state["fd"] = {"id":None,"data_solicitacao":hoje_iso(),"numero_pasta":"",
                                  "nome_assistido":"","demanda":"","assessor":"","status":"Pendente"}
    _perfil_dem = st.session_state.get("perfil","assessor")

    if "fd" in st.session_state:
        fd = st.session_state["fd"]
        with st.expander("✏️ Editar Demanda" if fd["id"] else "➕ Nova Demanda Avulsa", expanded=True):
            c1,c2,c3 = st.columns(3)
            with c1:
                dv   = datetime.date.fromisoformat(fd["data_solicitacao"]) if fd.get("data_solicitacao") else datetime.date.today()
                ds   = st.date_input("📅 Data da Solicitação", value=dv, key="fd_d")
                pasta= st.text_input("📁 Número da Pasta", value=fd.get("numero_pasta",""), key="fd_p", placeholder="Ex: 2026/045")
            with c2:
                nome  = st.text_input("👤 Nome do Assistido *", value=fd.get("nome_assistido",""), key="fd_n")
                optsA = ["(Não atribuído)"]+ASSESSORES
                idxA  = optsA.index(fd["assessor"]) if fd.get("assessor") in optsA else 0
                assess= st.selectbox("👨‍⚖️ Assessor", optsA, index=idxA, key="fd_a")
            with c3:
                if fd["id"]:
                    idxS  = STATUS_DEMANDA.index(fd["status"]) if fd.get("status") in STATUS_DEMANDA else 0
                    status= st.selectbox("📊 Status", STATUS_DEMANDA, index=idxS, key="fd_s")
                else:
                    status="Pendente"
                    st.info("Status inicial: **Pendente**")
            dem_txt = st.text_area("📝 Descrição da Demanda", value=fd.get("demanda",""), key="fd_dem", height=75)

            b1,b2,_ = st.columns([1,1,5])
            with b1:
                if st.button("💾 Salvar", type="primary", key="fd_save"):
                    if not nome.strip(): st.error("Nome do Assistido é obrigatório.")
                    else:
                        av = assess if assess != "(Não atribuído)" else ""
                        if fd["id"]:
                            atualizar_demanda(fd["id"],ds.isoformat(),pasta,nome,dem_txt,av,status,usuario)
                            st.success("✅ Demanda atualizada!")
                        else:
                            inserir_demanda(ds.isoformat(),pasta,nome,dem_txt,av,usuario)
                            st.success("✅ Demanda cadastrada!")
                        del st.session_state["fd"]; st.rerun()
            with b2:
                if st.button("❌ Cancelar", key="fd_cancel"):
                    del st.session_state["fd"]; st.rerun()

    fc1,fc2 = st.columns([2.5,1])
    with fc1: termo = st.text_input("🔍 Pesquisar demanda", placeholder="Nome, pasta, assessor...", key="dem_srch")
    with fc2: filtro_st = st.selectbox("Status", ["Todos","Pendente","Concluída"], key="dem_fst")

    dados = listar_demandas(None if filtro_st=="Todos" else filtro_st)
    if termo.strip():
        t = termo.strip().lower()
        dados = [d for d in dados if t in d.get("nome_assistido","").lower()
                 or t in (d.get("numero_pasta","") or "").lower()
                 or t in (d.get("assessor","") or "").lower()
                 or t in str(d.get("id",""))]

    if not dados: st.info("📪 Nenhuma demanda encontrada."); return
    st.caption(f"**{len(dados)}** demanda(s) · ordenadas por data de solicitação (mais antiga primeiro)")

    for d in dados:
        dias   = dias_aberto(d.get("data_solicitacao",""))
        ass    = (d.get("assessor","") or "—").split()[0]
        st_cls = STATUS_BADGE.get(d["status"],"")
        pasta  = d.get("numero_pasta","") or "—"

        with st.container(border=True):
            c1,c2,c3,c4,c5 = st.columns([0.6,3.2,2,1.1,0.9])
            with c1: st.markdown(f"**#{d['id']}**"); st.caption(pasta)
            with c2:
                st.markdown(f"**{d['nome_assistido']}**")
                if d.get("demanda"): st.caption((d["demanda"])[:80]+("…" if len(d.get("demanda",""))>80 else ""))
                st.caption(f"📅 {fmt_data(d.get('data_solicitacao',''))}")
            with c3:
                st.markdown(badge(d["status"],st_cls)+f'<br><span style="font-size:11px;color:#64748b;">👨‍⚖️ {ass}</span>', unsafe_allow_html=True)
            with c4: st.markdown(dias_html(dias), unsafe_allow_html=True)
            with c5:
                b1,b2 = st.columns(2)
                with b1:
                    if _perfil_dem == "assessor":
                        if st.button("✏️", key=f"ed_d_{d['id']}", help="Editar"):
                            st.session_state["fd"] = {"id":d["id"],"data_solicitacao":d.get("data_solicitacao",hoje_iso()),
                                "numero_pasta":d.get("numero_pasta",""),"nome_assistido":d["nome_assistido"],
                                "demanda":d.get("demanda",""),"assessor":d.get("assessor",""),"status":d.get("status","Pendente")}
                            st.rerun()
                with b2:
                    if _perfil_dem == "assessor":
                        if st.button("🗑️", key=f"dl_d_{d['id']}", help="Excluir"):
                            st.session_state[f"_dd_{d['id']}"] = True; st.rerun()

            if st.session_state.get(f"_dd_{d['id']}"):
                st.warning(f"⚠️ Confirma exclusão da demanda **#{d['id']}**?")
                cc1,cc2,_ = st.columns([1,1,5])
                with cc1:
                    if st.button("✅ Confirmar", key=f"cdd_{d['id']}", type="primary"):
                        deletar_demanda(d["id"]); del st.session_state[f"_dd_{d['id']}"]; st.rerun()
                with cc2:
                    if st.button("❌ Cancelar", key=f"cddc_{d['id']}"):
                        del st.session_state[f"_dd_{d['id']}"]; st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO: ATENDIMENTOS
# ══════════════════════════════════════════════════════════════════════════════
def modulo_atendimentos():
    usuario = st.session_state["nome_usuario"]
    perfil  = st.session_state["perfil"]
    section_title("🧑‍💼","Atendimentos")

    if st.button("➕ Registrar Novo Atendimento", type="primary"):
        st.session_state["fa"] = {"id":None,"data_atendimento":hoje_iso(),"nome_pessoa":"",
                                  "telefone":"","demanda":"","resolucao":"","assessor":""}

    if "fa" in st.session_state:
        fa = st.session_state["fa"]
        with st.expander("✏️ Editar Atendimento" if fa["id"] else "➕ Novo Atendimento", expanded=True):
            c1,c2 = st.columns(2)
            with c1:
                dv    = datetime.date.fromisoformat(fa["data_atendimento"]) if fa.get("data_atendimento") else datetime.date.today()
                dat   = st.date_input("📅 Data do Atendimento", value=dv, key="fa_d")
                nome  = st.text_input("👤 Nome da Pessoa *", value=fa.get("nome_pessoa",""), key="fa_n")
                tel   = st.text_input("📞 Telefone", value=fa.get("telefone",""), key="fa_t", placeholder="(27) 99999-9999")
                optsA = ["(Não atribuído)"]+ASSESSORES
                idxA  = optsA.index(fa["assessor"]) if fa.get("assessor") in optsA else 0
                assess= st.selectbox("👨‍⚖️ Assessor que Atendeu", optsA, index=idxA, key="fa_a")
            with c2:
                dem = st.text_area("📋 Demanda / Motivo do Atendimento", value=fa.get("demanda",""), key="fa_dem", height=100)
                res = st.text_area("✅ O que foi resolvido", value=fa.get("resolucao",""), key="fa_res", height=100)

            b1,b2,_ = st.columns([1,1,5])
            with b1:
                if st.button("💾 Salvar", type="primary", key="fa_save"):
                    if not nome.strip(): st.error("Nome da pessoa é obrigatório.")
                    else:
                        av = assess if assess != "(Não atribuído)" else ""
                        if fa["id"]:
                            atualizar_atendimento(fa["id"],dat.isoformat(),nome,tel,dem,res,av,usuario)
                            st.success("✅ Atendimento atualizado!")
                        else:
                            inserir_atendimento(dat.isoformat(),nome,tel,dem,res,av,usuario)
                            st.success("✅ Atendimento registrado!")
                        del st.session_state["fa"]; st.rerun()
            with b2:
                if st.button("❌ Cancelar", key="fa_cancel"):
                    del st.session_state["fa"]; st.rerun()

    fc1,fc2 = st.columns([2.5,1])
    with fc1: termo = st.text_input("🔍 Pesquisar atendimento", placeholder="Nome, telefone, demanda...", key="at_srch")
    with fc2:
        opts_f = ["Todos"]+[a.split()[0] for a in ASSESSORES]
        filtro_a = st.selectbox("Assessor", opts_f, key="at_fa")

    dados = listar_atendimentos()
    if filtro_a != "Todos":
        dados = [a for a in dados if (a.get("assessor","") or "").startswith(filtro_a)]
    if termo.strip():
        t = termo.strip().lower()
        dados = [a for a in dados if t in a.get("nome_pessoa","").lower()
                 or t in (a.get("telefone","") or "").lower()
                 or t in (a.get("demanda","") or "").lower()
                 or t in str(a.get("id",""))]

    if not dados: st.info("📪 Nenhum atendimento encontrado."); return
    st.caption(f"**{len(dados)}** atendimento(s)")

    for a in dados:
        ass = (a.get("assessor","") or "—").split()[0]
        with st.container(border=True):
            c1,c2,c3,c4 = st.columns([0.5,3.5,2.5,0.9])
            with c1: st.markdown(f"**#{a['id']}**"); st.caption(fmt_data(a.get("data_atendimento","")))
            with c2:
                st.markdown(f"**{a['nome_pessoa']}**")
                st.caption(f"📞 {a.get('telefone','') or '—'}")
                if a.get("demanda"): st.caption(f"📋 {a['demanda'][:70]}")
            with c3:
                st.markdown(f"👨‍⚖️ **{ass}**")
                if a.get("resolucao"): st.caption(f"✅ {a['resolucao'][:80]}")
            with c4:
                b1,b2 = st.columns(2)
                with b1:
                    if st.button("✏️", key=f"ed_a_{a['id']}", help="Editar"):
                        st.session_state["fa"] = {"id":a["id"],"data_atendimento":a.get("data_atendimento",hoje_iso()),
                            "nome_pessoa":a["nome_pessoa"],"telefone":a.get("telefone",""),
                            "demanda":a.get("demanda",""),"resolucao":a.get("resolucao",""),"assessor":a.get("assessor","")}
                        st.rerun()
                with b2:
                    if perfil == "assessor":
                        if st.button("🗑️", key=f"dl_a_{a['id']}", help="Excluir"):
                            st.session_state[f"_da_{a['id']}"] = True; st.rerun()

            if st.session_state.get(f"_da_{a['id']}"):
                st.warning(f"⚠️ Confirma exclusão do atendimento **#{a['id']} – {a['nome_pessoa']}**?")
                cc1,cc2,_ = st.columns([1,1,5])
                with cc1:
                    if st.button("✅ Confirmar", key=f"cda_{a['id']}", type="primary"):
                        deletar_atendimento(a["id"]); del st.session_state[f"_da_{a['id']}"]; st.rerun()
                with cc2:
                    if st.button("❌ Cancelar", key=f"cdac_{a['id']}"):
                        del st.session_state[f"_da_{a['id']}"]; st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO: RELATÓRIOS PDF
# ══════════════════════════════════════════════════════════════════════════════
def modulo_relatorios():
    section_title("📄","Relatórios em PDF — Formato A4 Paisagem")
    st.markdown(
        '<p style="color:#64748b;font-size:13px;margin-bottom:16px;">'
        'Todos os relatórios são gerados com a logo do Núcleo, cabeçalho oficial '
        'e layout profissional em formato A4 paisagem.</p>',
        unsafe_allow_html=True
    )

    TIPOS = {
        "processos_ativos":       "📌 Processos Ativos",
        "processos_aguardando":   "⏳ Processos Aguardando Docs",
        "processos_protocolados": "📨 Processos Protocolados",
        "processos_arquivados":   "📁 Arquivados",
        "demandas_avulsas":       "📋 Demandas Avulsas",
        "atendimentos":           "🧑‍💼 Atendimentos Realizados",
    }

    # ── Relatórios Rápidos (sem filtro de data) ─────────────────────────────
    st.markdown('<div class="sec-title" style="font-size:13px;">⚡ Relatórios Rápidos — todos os registros</div>',
                unsafe_allow_html=True)
    cols = st.columns(3)
    for i,(tipo,label) in enumerate(TIPOS.items()):
        with cols[i%3]:
            if st.button(label, key=f"rr_{tipo}", use_container_width=True):
                dados,titulo = _get_dados_relatorio(tipo,"")
                pdf = gerar_pdf(titulo,dados,tipo)
                if pdf:
                    st.download_button("⬇️ Baixar PDF", data=pdf,
                        file_name=f"naj-{tipo}-{hoje_iso()}.pdf",
                        mime="application/pdf",
                        key=f"dl_{tipo}", use_container_width=True)
                    st.success(f"✅ {len(dados)} registro(s).")
                else:
                    st.error("Instale: `pip install reportlab`")

    # ── Relatório Personalizado (assessor + período) ─────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sec-title" style="font-size:13px;">🔍 Relatório Personalizado — filtros por assessor e/ou período</div>',
                unsafe_allow_html=True)

    with st.container(border=True):
        # Linha 1: tipo + assessor
        c1, c2 = st.columns(2)
        with c1:
            tipo_sel = st.selectbox(
                "Tipo de Relatório",
                list(TIPOS.keys()),
                format_func=lambda k: TIPOS[k],
                key="rp_t"
            )
        with c2:
            ass_opts = ["(Todos os assessores)"] + ASSESSORES
            ass_sel  = st.selectbox("Assessor", ass_opts, key="rp_a")

        # Linha 2: período
        st.markdown(
            '<div style="font-size:13px;font-weight:600;color:#1e3a8a;margin:12px 0 6px;">'
            '📅 Filtrar por período (opcional)</div>',
            unsafe_allow_html=True
        )

        # Período rápido + datas manuais na mesma linha
        pc1, pc2, pc3, pc4 = st.columns([1.4, 1, 1, 1])
        with pc1:
            periodo_rapido = st.selectbox(
                "Atalho de período",
                ["Personalizado", "Hoje", "Esta semana", "Este mês", "Este ano", "Sem filtro de data"],
                key="rp_periodo",
                label_visibility="collapsed"
            )

        # Calcular datas padrão conforme atalho
        hoje   = datetime.date.today()
        if periodo_rapido == "Hoje":
            default_ini, default_fim = hoje, hoje
        elif periodo_rapido == "Esta semana":
            default_ini = hoje - datetime.timedelta(days=hoje.weekday())
            default_fim = hoje
        elif periodo_rapido == "Este mês":
            default_ini = hoje.replace(day=1)
            default_fim = hoje
        elif periodo_rapido == "Este ano":
            default_ini = hoje.replace(month=1, day=1)
            default_fim = hoje
        else:
            default_ini, default_fim = hoje.replace(month=1, day=1), hoje

        usar_data = (periodo_rapido != "Sem filtro de data")

        with pc2:
            data_ini = st.date_input(
                "De", value=default_ini, key="rp_ini",
                disabled=not usar_data,
                label_visibility="visible"
            )
        with pc3:
            data_fim = st.date_input(
                "Até", value=default_fim, key="rp_fim",
                disabled=not usar_data,
                label_visibility="visible"
            )
        with pc4:
            st.markdown("<br>", unsafe_allow_html=True)  # alinhamento vertical

        # Aviso de data inválida
        if usar_data and data_ini > data_fim:
            st.warning("⚠️ A data inicial não pode ser maior que a data final.")

        # Botão gerar
        if st.button("📄 Gerar Relatório Personalizado", type="primary", key="btn_rp"):
            af  = "" if ass_sel == ass_opts[0] else ass_sel
            ini = data_ini if usar_data else None
            fim = data_fim if usar_data else None

            if usar_data and ini and fim and ini > fim:
                st.error("Corrija o período antes de gerar.")
            else:
                dados, titulo = _get_dados_relatorio(tipo_sel, af, ini, fim)
                pdf = gerar_pdf(titulo, dados, tipo_sel, af)

                # Monta descrição do filtro para feedback
                partes = []
                if af:
                    partes.append(f"assessor: {af.split()[0]}")
                if usar_data and ini and fim:
                    partes.append(f"período: {fmt_data(ini.isoformat())} a {fmt_data(fim.isoformat())}")
                descricao_filtro = " | ".join(partes) if partes else "sem filtros adicionais"

                if pdf:
                    st.download_button(
                        "⬇️ Baixar Relatório Personalizado",
                        data=pdf,
                        file_name=f"naj-personalizado-{hoje_iso()}.pdf",
                        mime="application/pdf",
                        key="dl_rp"
                    )
                    if dados:
                        st.success(f"✅ {len(dados)} registro(s) encontrado(s) — {descricao_filtro}.")
                    else:
                        st.warning(f"⚠️ Nenhum registro encontrado com os filtros aplicados ({descricao_filtro}).")
                else:
                    st.error("Instale: `pip install reportlab`")
# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    init_db()
    inject_css()

    if not st.session_state.get("logado"):
        tela_login()
        return

    menu = render_sidebar()
    render_header()

    exibir_notificacoes()

    if   "Dashboard"    in menu: modulo_dashboard()
    elif "Ativos"       in menu: modulo_processos("ativos")
    elif "Protocolados" in menu: modulo_processos("protocolados")
    elif "Arquivados"   in menu: modulo_processos("arquivados")
    elif "Demandas"     in menu: modulo_demandas()
    elif "Atendimentos" in menu: modulo_atendimentos()
    elif "Relatórios"   in menu: modulo_relatorios()

if __name__ == "__main__":
    main()
