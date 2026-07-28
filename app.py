import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import urllib.parse
import base64
import psycopg2
from psycopg2.extras import RealDictCursor
import io
import os

# --- CONFIGURAÇÕES DA PÁGINA E IDENTIDADE VISUAL ---
st.set_page_config(page_title="Central de Operações", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #fdfdfd; }
    h1, h2, h3 { color: #4a0e4e; }
    .stButton>button { background-color: #8b0000; color: white; font-weight: bold; border-radius: 6px; border: none; transition: 0.3s; }
    .stButton>button:hover { background-color: #4a0e4e; color: white; border: 1px solid #8b0000; }
    div[data-testid="stSidebar"] { background-color: #4a0e4e; }
    div[data-testid="stSidebar"] * { color: white; }
    
    /* Estilização das Abas */
    button[data-testid="stTab"] { background-color: transparent; border-radius: 5px 5px 0 0; }
    button[data-testid="stTab"][aria-selected="true"] {
        background-color: #4a0e4e !important;
        border-bottom: 4px solid #8b0000 !important;
    }
    button[data-testid="stTab"][aria-selected="true"] * { color: white !important; font-weight: bold; }
    
    /* Ajuste para pastas */
    div[data-testid="stExpander"] { border-left: 4px solid #4a0e4e; }
    div[role="radiogroup"] { flex-wrap: wrap; gap: 15px; }
    
    .ficha-box { border: 2px solid #4a0e4e; padding: 20px; border-radius: 10px; background-color: #fafafa; margin-top: 15px;}
</style>
""", unsafe_allow_html=True)

# --- CONEXÃO COM SUPABASE (POSTGRESQL) ---
def get_db_connection():
    try:
        return psycopg2.connect(st.secrets["SUPABASE_URL"])
    except Exception as e:
        st.error(f"Erro de conexão com a Nuvem (Supabase): {e}")
        st.stop()

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS empresas (id SERIAL PRIMARY KEY, nome TEXT, cnpj TEXT, endereco TEXT, telefone TEXT, responsavel TEXT, servicos TEXT DEFAULT 'Ambos (Furto/Roubo + Monitoramento)', valor_veiculo REAL DEFAULT 3.00, dia_vencimento INTEGER DEFAULT 10, status_pagamento TEXT DEFAULT 'Pendente', valor_pago REAL DEFAULT 0.00, logo_binario BYTEA)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico_faturas (id SERIAL PRIMARY KEY, mes_ref TEXT, empresa TEXT, total_veiculos INTEGER, valor_unitario REAL, valor_pago REAL, status TEXT, data_pagamento TEXT)''')
    
    try:
        c.execute("ALTER TABLE empresas ADD COLUMN IF NOT EXISTS valor_pago REAL DEFAULT 0.00;")
        c.execute("ALTER TABLE empresas ADD COLUMN IF NOT EXISTS logo_binario BYTEA;")
        conn.commit()
    except Exception:
        conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS clientes (id SERIAL PRIMARY KEY, nome TEXT, documento TEXT, endereco TEXT, telefone TEXT, empresa TEXT, status TEXT DEFAULT 'Ativo')''')
    c.execute('''CREATE TABLE IF NOT EXISTS veiculos (id SERIAL PRIMARY KEY, cliente_id INTEGER REFERENCES clientes(id) ON DELETE CASCADE, tipo_veic TEXT, placa TEXT, modelo TEXT, cor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico (id SERIAL PRIMARY KEY, data_hora TEXT, cliente TEXT, placa TEXT, tipo TEXT, status TEXT, detalhes TEXT, empresa TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS auditoria (id SERIAL PRIMARY KEY, data_hora TEXT, acao TEXT, modulo TEXT, detalhes TEXT, usuario TEXT)''')
    conn.commit()
    conn.close()

# CACHE ATIVO PARA MANTÊ-R O APLICATIVO RÁPIDO
@st.cache_data(ttl=120, show_spinner=False)
def fetch_data(query, params=()):
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute(query, params)
    data = c.fetchall()
    conn.close()
    return data

def fetch_logo_direto(query, params=()):
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute(query, params)
    data = c.fetchall()
    conn.close()
    return data

def execute_query(query, params=()):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()
    st.cache_data.clear()

init_db()

# --- FUNÇÕES ÚTEIS E REGRAS DE NEGÓCIO ---
def get_horario_brasil():
    fuso_br = timezone(timedelta(hours=-3))
    return datetime.now(fuso_br)

def get_horario_brasil_str():
    return get_horario_brasil().strftime("%d/%m/%Y %H:%M:%S")

def registrar_auditoria(acao, modulo, detalhes):
    usuario = st.session_state.get('nome_empresa', 'AD RASTREAMENTO VEICULAR')
    agora = get_horario_brasil_str()
    execute_query("INSERT INTO auditoria (data_hora, acao, modulo, detalhes, usuario) VALUES (%s,%s,%s,%s,%s)", 
                  (agora, acao, modulo, detalhes, usuario))

def calcular_status_fatura(status_banco, dia_venc):
    if status_banco == "Pago": return "🟢 Em Dias (Pago)"
    dia_atual = get_horario_brasil().day
    dia_fechamento = dia_venc - 2 if (dia_venc - 2) > 0 else 1

    if dia_atual == dia_venc: return "🟠 Vence Hoje"
    elif dia_atual > dia_venc: return "🔴 Vencida / Atrasada"
    elif dia_atual >= dia_fechamento and dia_atual < dia_venc: return "🟡 Fatura Fechada (Próxima ao Vencimento)"
    else: return "🟢 Em Dias"

def gerar_link_whatsapp(contexto):
    telefone = "5584999305771"
    mensagem = urllib.parse.quote(f"Olá, AD Rastreamento Veicular! Preciso de suporte/ajuda na Central de Operações.\n\n📍 Contexto: {contexto}")
    link = f"https://wa.me/{telefone}?text={mensagem}"
    return f'<a href="{link}" target="_blank" style="text-decoration:none;"><button style="background-color:#25D366; color:white; padding:10px 15px; border-radius:5px; border:none; font-weight:bold; cursor:pointer; width:100%;">💬 Solicitar Suporte via WhatsApp</button></a>'

def gerar_relatorio_html(dados_relatorio, empresa_nome):
    html_content = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>Relatório de Ocorrência</title>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; margin: 40px; }}
            .header {{ text-align: center; border-bottom: 3px solid #4a0e4e; padding-bottom: 15px; margin-bottom: 30px; }}
            .header h1 {{ color: #4a0e4e; margin: 0; }}
            .header h3 {{ color: #8b0000; margin: 5px 0 0 0; }}
            .content {{ background: #f9f9f9; border: 1px solid #ddd; padding: 25px; border-radius: 8px; }}
            .field {{ margin-bottom: 15px; }}
            .label {{ font-weight: bold; color: #4a0e4e; }}
            .footer {{ margin-top: 40px; text-align: center; font-size: 12px; color: #777; border-top: 1px solid #ddd; padding-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🛡️ CENTRAL DE OPERAÇÕES</h1>
            <h3>Relatório Oficial de Atendimento Operacional</h3>
        </div>
        <div class="content">
            <div class="field"><span class="label">Empresa Responsável:</span> {empresa_nome}</div>
            <div class="field"><span class="label">ID do Registro:</span> {dados_relatorio['id']}</div>
            <div class="field"><span class="label">Data e Hora:</span> {dados_relatorio['data_hora']}</div>
            <div class="field"><span class="label">Cliente:</span> {dados_relatorio['cliente']}</div>
            <div class="field"><span class="label">Placa do Veículo:</span> {dados_relatorio['placa']}</div>
            <div class="field"><span class="label">Tipo de Ocorrência:</span> {dados_relatorio['tipo']}</div>
            <div class="field"><span class="label">Status Atual:</span> {dados_relatorio['status']}</div>
            <hr style="border: 0; border-top: 1px solid #ccc; margin: 20px 0;">
            <div class="field"><span class="label">Detalhes / Dinâmica / Desfecho:</span><br><p>{dados_relatorio['detalhes']}</p></div>
        </div>
        <div class="footer">
            Documento gerado automaticamente pela Central de Operações de Segurança.
        </div>
    </body>
    </html>
    """
    b64 = base64.b64encode(html_content.encode('utf-8')).decode("utf-8")
    return f'<a href="data:text/html;base64,{b64}" download="Relatorio_{dados_relatorio["placa"]}.html" target="_blank"><button style="background-color:#4a0e4e; color:white; padding:10px 15px; border-radius:5px; border:none; font-weight:bold; cursor:pointer;">📄 Baixar Relatório Oficial (HTML/PDF)</button></a>'

# --- CONTROLE DE SESSÃO SEGURO ---
if 'logged_in' not in st.session_state:
    if st.query_params.get("logged_in") == "true":
        st.session_state.logged_in = True
        st.session_state.is_admin = (st.query_params.get("admin") == "true")
        st.session_state.nome_empresa = st.query_params.get("empresa", "")
    else:
        st.session_state.logged_in = False
        st.session_state.is_admin = False
        st.session_state.nome_empresa = ""

if 'acao_clientes' not in st.session_state:
    st.session_state.acao_clientes = "Listar"

if 'num_veiculos_form' not in st.session_state:
    st.session_state.num_veiculos_form = 1

if 'reset_keys' not in st.session_state:
    st.session_state.reset_keys = {
        'ficha_cli': 0, 'edit_cli': 0, 'rel_fr': 0, 
        'rel_mon': 0, 'edit_emp': 0, 'aud_del': 0, 'fin_pgto': 0
    }

if 'flash_msg' in st.session_state:
    st.toast(st.session_state.flash_msg, icon="✅")
    del st.session_state.flash_msg

# ==========================================
# 1. TELA DE LOGIN
# ==========================================
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>🛡️ Central de Operações de Segurança</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #8b0000; font-weight: bold;'>Administrador: AD Rastreamento Veicular</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            user = st.text_input("Usuário ou Nome da Empresa")
            senha = st.text_input("Senha ou CNPJ", type="password")
            submit = st.form_submit_button("Entrar no Sistema")
            
            if submit:
                if user == "AD" and senha == "admin":
                    st.session_state.logged_in = True
                    st.session_state.is_admin = True
                    st.session_state.nome_empresa = "AD RASTREAMENTO VEICULAR"
                    st.query_params["logged_in"] = "true"
                    st.query_params["admin"] = "true"
                    st.query_params["empresa"] = "AD RASTREAMENTO VEICULAR"
                    st.rerun()
                else:
                    res = fetch_data("SELECT nome FROM empresas WHERE nome=%s AND cnpj=%s", (user, senha))
                    if res:
                        st.session_state.logged_in = True
                        st.session_state.is_admin = False
                        st.session_state.nome_empresa = res[0]['nome']
                        st.query_params["logged_in"] = "true"
                        st.query_params["admin"] = "false"
                        st.query_params["empresa"] = res[0]['nome']
                        registrar_auditoria("Acesso", "Login", f"{res[0]['nome']} acessou o sistema.")
                        st.rerun()
                    else:
                        st.error("Acesso Negado: Login ou Senha incorretos.")
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(gerar_link_whatsapp("Tela de Login - Tentativa de acesso / Dúvida com Senha"), unsafe_allow_html=True)

# ==========================================
# 2. SISTEMA PRINCIPAL
# ==========================================
else:
    with st.sidebar:
        if not st.session_state.is_admin:
            try:
                res_logo_sb = fetch_logo_direto("SELECT logo_binario FROM empresas WHERE nome=%s", (st.session_state.nome_empresa,))
                if res_logo_sb and len(res_logo_sb) > 0:
                    logo_dado = res_logo_sb[0].get('logo_binario')
                    if logo_dado is not None:
                        logo_bytes = bytes(logo_dado) if isinstance(logo_dado, memoryview) else bytes(logo_dado)
                        if len(logo_bytes) > 10:
                            st.image(io.BytesIO(logo_bytes), width=140)
            except Exception:
                pass

        st.write(f"👤 **Conectado como:** {st.session_state.nome_empresa}")
        
        if not st.session_state.is_admin:
            with st.expander("🖼️ Enviar / Alterar Minha Logo"):
                up_logo = st.file_uploader("Escolha a imagem (PNG/JPG)", type=["png", "jpg", "jpeg"], key="up_logo_parceiro")
                if up_logo is not None:
                    bytes_img = up_logo.getvalue()
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("UPDATE empresas SET logo_binario = %s WHERE nome = %s", (bytes_img, st.session_state.nome_empresa))
                    conn.commit()
                    conn.close()
                    st.cache_data.clear()
                    st.success("Logo atualizada com sucesso!")
                    st.rerun()

        if st.button("🚪 Sair do Sistema"):
            st.session_state.logged_in = False
            st.session_state.is_admin = False
            st.session_state.nome_empresa = ""
            st.query_params.clear()
            st.rerun()
        st.markdown("---")
        st.markdown("### 🛡️ Missão AD")
        st.markdown("**Foco total na segurança, agilidade e comprometimento.** Nossa missão é garantir proteção máxima e resposta rápida para a nossa frota e a de nossos parceiros.")
        st.markdown("---")
        st.markdown("### 📞 Suporte Oficial")
        st.markdown(gerar_link_whatsapp(f"Menu Sidebar - Empresa Logada: {st.session_state.nome_empresa}"), unsafe_allow_html=True)

    if st.session_state.is_admin:
        abas = ["🚨 Central 24h", "👤 Clientes", "📖 Relatórios", "🏢 Empresas", "💰 Financeiro", "🕵️ Auditoria"]
    else:
        abas = ["👤 Clientes", "📖 Relatórios", "💰 Meu Faturamento"]
        
    tabs = st.tabs(abas)
    tab_idx = 0

    # --- ABA: OPERAÇÃO 24H (SÓ ADMIN) ---
    if st.session_state.is_admin:
        with tabs[tab_idx]:
            st.header("🚨 Central de Operações e Ocorrências 24h")
            
            with st.form("form_busca_veic", clear_on_submit=False):
                busca_op = st.text_input("🔍 Buscar veículo (Digite Nome, Placa ou CPF)")
                btn_buscar = st.form_submit_button("Pesquisar Veículo")
            
            if btn_buscar and busca_op and len(busca_op) >= 3:
                st.session_state["termo_busca_ativo"] = busca_op
                
            if "termo_busca_ativo" in st.session_state and st.session_state["termo_busca_ativo"]:
                termo = f"%{st.session_state['termo_busca_ativo'].lower()}%"
                q_busca = """
                    SELECT c.nome, c.documento, c.telefone, c.empresa, v.placa, v.modelo, v.cor, v.tipo_veic 
                    FROM clientes c JOIN veiculos v ON c.id = v.cliente_id 
                    WHERE c.status='Ativo' AND (lower(c.nome) LIKE %s OR lower(v.placa) LIKE %s OR lower(c.documento) LIKE %s)
                """
                resultados = fetch_data(q_busca, (termo, termo, termo))
                
                if resultados:
                    st.success("Veículos encontrados! Selecione abaixo.")
                    placas_disponiveis = [f"{r['placa']} - {r['nome']} ({r['modelo']})" for r in resultados]
                    placa_sel_texto = st.selectbox("Selecione o Veículo para Atendimento:", placas_disponiveis)
                    
                    if placa_sel_texto:
                        placa_sel = placa_sel_texto.split(" - ")[0]
                        info_veic = next(item for item in resultados if item["placa"] == placa_sel)
                        
                        st.markdown("---")
                        tipo_servico = st.radio("📋 **Ação na Central:**", ["Abertura de Furto/Roubo", "Monitoramento Técnico"], horizontal=True)
                        
                        if tipo_servico == "Abertura de Furto/Roubo":
                            with st.form("form_furto", clear_on_submit=True):
                                st.markdown("<h3 style='color: #8b0000;'>Abertura de Furto/Roubo (Início Automático)</h3>", unsafe_allow_html=True)
                                tipo_oc = st.selectbox("Natureza", ["Furto", "Roubo"])
                                local_oc = st.text_input("Localização do Fato")
                                desc_oc = st.text_area("Descrição / Dinâmica")
                                st.info("ℹ️ Status inicial configurado automaticamente como: EM ANDAMENTO.")
                                
                                if st.form_submit_button("Salvar Ocorrência"):
                                    agora = get_horario_brasil_str()
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (%s,%s,%s,%s,%s,%s,%s)", 
                                                  (agora, info_veic['nome'], placa_sel, tipo_oc, "EM ANDAMENTO", f"Local: {local_oc} | {desc_oc}", info_veic['empresa']))
                                    registrar_auditoria("Registro", "Operação", f"Ocorrência de {tipo_oc} INICIADA para {placa_sel}")
                                    st.session_state["termo_busca_ativo"] = ""
                                    st.session_state.flash_msg = "Salvo e enviado para relatórios como EM ANDAMENTO!"
                                    st.rerun()
                        
                        elif tipo_servico == "Monitoramento Técnico":
                            with st.form("form_monitoramento", clear_on_submit=True):
                                st.markdown("<h3 style='color: #4a0e4e;'>Monitoramento Técnico</h3>", unsafe_allow_html=True)
                                evento_mon = st.selectbox("Evento", ["Cerca Virtual", "Desconexão de Bateria", "Falta de Comunicação", "Outros"])
                                acao_mon = st.text_area("Ação da Central")
                                if st.form_submit_button("Salvar Monitoramento"):
                                    agora = get_horario_brasil_str()
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (%s,%s,%s,%s,%s,%s,%s)", 
                                                  (agora, info_veic['nome'], placa_sel, "Monitoramento", "FINALIZADO", f"Evento: {evento_mon} | Ação: {acao_mon}", info_veic['empresa']))
                                    registrar_auditoria("Registro", "Monitoramento", f"Evento para {placa_sel}")
                                    st.session_state["termo_busca_ativo"] = ""
                                    st.session_state.flash_msg = "Salvo com sucesso!"
                                    st.rerun()
                else:
                    st.warning("Nenhum veículo encontrado com este termo.")
        tab_idx += 1

    # --- ABA: CLIENTES E FROTAS ---
    with tabs[tab_idx]:
        st.header("👤 Gerenciamento de Clientes e Frotas Multi-Veículos")
        
        acao_clientes = st.radio("Ação Clientes:", ["Listar", "Incluir Novo", "Importação em Lote", "Editar", "Excluir"], horizontal=True)
        st.markdown("---")
        
        empresas_disp = fetch_data("SELECT nome FROM empresas")
        opcoes_emp = [e['nome'] for e in empresas_disp] if st.session_state.is_admin else [st.session_state.nome_empresa]

        if acao_clientes == "Listar":
            q_completa = """
                SELECT c.id, c.nome, c.documento, c.endereco, c.telefone, v.tipo_veic, v.placa, v.modelo, v.cor, c.empresa, c.status 
                FROM clientes c JOIN veiculos v ON c.id = v.cliente_id
            """
            if not st.session_state.is_admin:
                q_completa += f" WHERE c.empresa='{st.session_state.nome_empresa}'"
            
            res_geral = fetch_data(q_completa)
            
            if res_geral:
                df_geral = pd.DataFrame(res_geral)
                st.download_button(label="📥 Baixar Base Completa de Frotas (CSV)", data=df_geral.to_csv(index=False).encode('utf-8'), file_name="Base_Clientes_Frotas.csv", mime="text/csv")
                
                empresas_ativas = df_geral['empresa'].unique()
                for emp_ativa in empresas_ativas:
                    with st.expander(f"📁 Clientes e Frotas da Empresa: {emp_ativa}"):
                        df_emp = df_geral[df_geral['empresa'] == emp_ativa]
                        st.dataframe(df_emp[['nome', 'documento', 'placa', 'modelo', 'cor', 'status']], use_container_width=True)
                
                st.markdown("---")
                st.subheader("🔍 Visualizar Ficha Completa do Cliente")
                
                q_clientes_validos = """
                    SELECT DISTINCT c.id, c.nome, c.documento, c.empresa 
                    FROM clientes c 
                    JOIN veiculos v ON c.id = v.cliente_id
                """
                if not st.session_state.is_admin:
                    q_clientes_validos += f" WHERE c.empresa='{st.session_state.nome_empresa}'"
                
                clientes_para_ficha = fetch_data(q_clientes_validos)
                lista_ficha_op = [""] + [f"{cli['id']} - {cli['nome']} (CPF/CNPJ: {cli['documento']}) - [{cli['empresa']}]" for cli in clientes_para_ficha]
                
                k_ficha_cli = st.session_state.reset_keys['ficha_cli']
                cli_ficha_sel = st.selectbox("Selecione o cliente para ver a ficha completa e seus veículos:", lista_ficha_op, key=f"sb_ficha_cli_{k_ficha_cli}")
                
                if cli_ficha_sel != "":
                    id_cli_ficha = int(cli_ficha_sel.split(" - ")[0])
                    dados_cli_ficha = fetch_data("SELECT * FROM clientes WHERE id=%s", (id_cli_ficha,))[0]
                    veiculos_cli_ficha = fetch_data("SELECT * FROM veiculos WHERE cliente_id=%s", (id_cli_ficha,))
                    
                    if st.button("❌ Fechar Ficha Cadastral", key="btn_close_ficha_cli"):
                        st.session_state.reset_keys['ficha_cli'] += 1
                        st.rerun()

                    st.markdown(f"""
                    <div class="ficha-box">
                        <h3 style="color:#4a0e4e; margin-top:0;">📋 Ficha Cadastral Completa</h3>
                        <p><b>Nome do Cliente:</b> {dados_cli_ficha['nome']}</p>
                        <p><b>CPF / CNPJ:</b> {dados_cli_ficha['documento']}</p>
                        <p><b>Endereço:</b> {dados_cli_ficha['endereco']}</p>
                        <p><b>Telefone:</b> {dados_cli_ficha['telefone']}</p>
                        <p><b>Empresa Responsável:</b> {dados_cli_ficha['empresa']}</p>
                        <p><b>Status:</b> {dados_cli_ficha['status']}</p>
                        <hr style="border: 0; border-top: 2px solid #4a0e4e; margin: 15px 0;">
                        <h4 style="color:#8b0000;">🚗 Veículos / Frotas Vinculadas ({len(veiculos_cli_ficha)})</h4>
                    """, unsafe_allow_html=True)
                    
                    if veiculos_cli_ficha:
                        df_veics = pd.DataFrame(veiculos_cli_ficha)[['tipo_veic', 'placa', 'modelo', 'cor']]
                        df_veics.columns = ['Tipo', 'Placa', 'Modelo', 'Cor']
                        st.dataframe(df_veics, use_container_width=True)
                    else:
                        st.info("Nenhum veículo vinculado a este cliente.")
                        
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("Nenhum cliente ou veículo cadastrado no momento.")
                
        elif acao_clientes == "Incluir Novo":
            if not opcoes_emp:
                st.error("Nenhuma empresa parceira cadastrada! Cadastre a empresa primeiro.")
            else:
                st.subheader("📝 Cadastro de Novo Cliente e Seus Veículos")
                
                with st.form("form_cadastro_multiplo", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    nome_cli = c1.text_input("Nome do Cliente *")
                    doc_cli = c2.text_input("CPF / CNPJ *")
                    end_cli = c1.text_input("Endereço")
                    tel_cli = c2.text_input("Telefone")
                    emp_cli = c1.selectbox("Empresa (Pasta) *", opcoes_emp)
                    
                    st.markdown("---")
                    st.write("🚗 **Frota / Veículos do Cliente:**")
                    
                    col_b1, col_b2 = st.columns([1, 4])
                    with col_b1:
                        if st.form_submit_button("➕ Adicionar Veículo"):
                            st.session_state.num_veiculos_form += 1
                            st.rerun()
                    with col_b2:
                        if st.session_state.num_veiculos_form > 1:
                            if st.form_submit_button("➖ Remover Último Veículo"):
                                st.session_state.num_veiculos_form -= 1
                                st.rerun()

                    veiculos_dados = []
                    for i in range(st.session_state.num_veiculos_form):
                        st.markdown(f"**Veículo {i+1}**")
                        vc1, vc2, vc3, vc4 = st.columns(4)
                        t_veic = vc1.selectbox(f"Tipo {i+1}", ["Carro", "Moto", "Caminhão", "Outro"], key=f"t_{i}")
                        p_veic = vc2.text_input(f"Placa * {i+1}", key=f"p_{i}")
                        m_veic = vc3.text_input(f"Modelo {i+1}", key=f"m_{i}")
                        c_veic = vc4.text_input(f"Cor {i+1}", key=f"c_{i}")
                        veiculos_dados.append({"tipo": t_veic, "placa": p_veic, "modelo": m_veic, "cor": c_veic})
                        st.markdown("---")

                    btn_salvar_tudo = st.form_submit_button("💾 Salvar Cadastro Completo")
                    
                    if btn_salvar_tudo:
                        if nome_cli and doc_cli and any(v['placa'] for v in veiculos_dados):
                            conn = get_db_connection()
                            cur = conn.cursor(cursor_factory=RealDictCursor)
                            cur.execute("INSERT INTO clientes (nome, documento, endereco, telefone, empresa, status) VALUES (%s,%s,%s,%s,%s,'Ativo') RETURNING id", 
                                           (nome_cli, doc_cli, end_cli, tel_cli, emp_cli))
                            cliente_id = cur.fetchone()['id']
                            
                            validos = [v for v in veiculos_dados if v['placa'].strip()]
                            for v in validos:
                                cur.execute("INSERT INTO veiculos (cliente_id, tipo_veic, placa, modelo, cor) VALUES (%s,%s,%s,%s,%s)", 
                                               (cliente_id, v['tipo'], v['placa'], v['modelo'], v['cor']))
                            conn.commit()
                            conn.close()
                            st.cache_data.clear()
                            
                            total_cad = len(validos)
                            msg_veic = f"1 veículo" if total_cad == 1 else f"{total_cad} veículos"

                            st.session_state.num_veiculos_form = 1
                            registrar_auditoria("Cadastro", "Clientes", f"Cliente {nome_cli} cadastrado com {msg_veic}.")
                            st.session_state.flash_msg = "Cliente e veículos cadastrados com sucesso e tela limpa!"
                            st.rerun()
                        else:
                            st.error("Preencha o Nome, CPF/CNPJ e pelo menos a Placa de um veículo.")
                            
        elif acao_clientes == "Importação em Lote":
            st.subheader("📥 Importação Inteligente de Clientes e Frotas via CSV")
            st.info("O sistema criará o cliente automaticamente (se já não existir pelo CPF/CNPJ) e agrupará os veículos na conta dele.")
            
            emp_lote = st.selectbox("Selecione a Empresa de destino:", opcoes_emp, key="emp_lote_sel")
            
            df_exemplo = pd.DataFrame({
                "Nome": ["João da Silva", "João da Silva"],
                "Documento": ["123.456.789-00", "123.456.789-00"],
                "Endereço": ["Rua A, 100", "Rua A, 100"],
                "Telefone": ["(84) 99999-1111", "(84) 99999-1111"],
                "Tipo Veículo": ["Carro", "Moto"],
                "Placa": ["ABC-1234", "XYZ-5678"],
                "Modelo": ["Fiat Palio", "Honda CG"],
                "Cor": ["Prata", "Vermelha"]
            })
            st.download_button(label="📄 Baixar Planilha Modelo (CSV)", data=df_exemplo.to_csv(index=False).encode('utf-8'), file_name="Modelo_Importacao.csv", mime="text/csv")
            
            arquivo_csv = st.file_uploader("Escolha o arquivo CSV", type=["csv"])
            if arquivo_csv is not None:
                try:
                    df_import = pd.read_csv(arquivo_csv)
                    if st.button("🚀 Processar Importação"):
                        importados = 0
                        for _, row in df_import.iterrows():
                            nome = str(row.get("Nome", ""))
                            doc = str(row.get("Documento", ""))
                            end = str(row.get("Endereço", ""))
                            tel = str(row.get("Telefone", ""))
                            tipo = str(row.get("Tipo Veículo", "Carro"))
                            placa = str(row.get("Placa", ""))
                            modelo = str(row.get("Modelo", ""))
                            cor = str(row.get("Cor", ""))
                            
                            if nome and placa:
                                conn = get_db_connection()
                                cur = conn.cursor(cursor_factory=RealDictCursor)
                                cur.execute("SELECT id FROM clientes WHERE documento=%s AND empresa=%s", (doc, emp_lote))
                                cli_res = cur.fetchone()
                                
                                if cli_res:
                                    cli_id = cli_res['id']
                                else:
                                    cur.execute("INSERT INTO clientes (nome, documento, endereco, telefone, empresa, status) VALUES (%s,%s,%s,%s,%s,'Ativo') RETURNING id", 
                                                (nome, doc, end, tel, emp_lote))
                                    cli_id = cur.fetchone()['id']
                                    
                                cur.execute("INSERT INTO veiculos (cliente_id, tipo_veic, placa, modelo, cor) VALUES (%s,%s,%s,%s,%s)", 
                                            (cli_id, tipo, placa, modelo, cor))
                                conn.commit()
                                conn.close()
                                importados += 1
                        
                        st.cache_data.clear()        
                        registrar_auditoria("Importação Lote", "Clientes", f"{importados} registros importados via CSV.")
                        st.session_state.flash_msg = f"Importação concluída! {importados} registros processados."
                        st.rerun()
                except Exception as e:
                    st.error(f"Erro ao processar CSV: {e}")
            
        elif acao_clientes in ["Editar", "Excluir"]:
            with st.form("form_busca_cliente", clear_on_submit=False):
                busca = st.text_input("🔍 Buscar Cliente por Nome, Placa ou CPF:")
                btn_pesq = st.form_submit_button("Pesquisar")
                
            if btn_pesq and busca and len(busca) >= 3:
                st.session_state["termo_cli_ativo"] = busca
                
            if "termo_cli_ativo" in st.session_state and st.session_state["termo_cli_ativo"]:
                termo_c = f"%{st.session_state['termo_cli_ativo'].lower()}%"
                q_cli_busca = """
                    SELECT DISTINCT c.id, c.nome, c.documento FROM clientes c 
                    JOIN veiculos v ON c.id = v.cliente_id 
                    WHERE (lower(c.nome) LIKE %s OR lower(v.placa) LIKE %s OR lower(c.documento) LIKE %s)
                """
                if not st.session_state.is_admin:
                    q_cli_busca += f" AND c.empresa='{st.session_state.nome_empresa}'"
                
                res_cli_busca = fetch_data(q_cli_busca, (termo_c, termo_c, termo_c))
                if res_cli_busca:
                    opcoes_cli = [f"{item['id']} - {item['nome']} (CPF/CNPJ: {item['documento']})" for item in res_cli_busca]
                    
                    k_edit_cli = st.session_state.reset_keys['edit_cli']
                    cli_escolhido = st.selectbox("Selecione o Cliente:", [""] + opcoes_cli, key=f"sb_edit_cli_{k_edit_cli}")
                    
                    if cli_escolhido != "":
                        if st.button("❌ Fechar Seleção", key="btn_close_edit_cli"):
                            st.session_state.reset_keys['edit_cli'] += 1
                            st.rerun()
                            
                        id_c_sel = int(cli_escolhido.split(" - ")[0])
                        dados_cliente_sel = fetch_data("SELECT * FROM clientes WHERE id=%s", (id_c_sel,))[0]
                        veiculos_cliente = fetch_data("SELECT * FROM veiculos WHERE cliente_id=%s", (id_c_sel,))
                        
                        st.markdown(f"**Cliente:** {dados_cliente_sel['nome']} | **Documento:** {dados_cliente_sel['documento']}")
                        st.write("🚗 **Veículos vinculados:**")
                        for v in veiculos_cliente:
                            st.write(f"- Placa: **{v['placa']}** | Modelo: {v['modelo']} | Cor: {v['cor']}")
                            
                        if acao_clientes == "Editar":
                            with st.form(f"form_edit_cad_{id_c_sel}", clear_on_submit=True):
                                st.write("**Atualizando Dados:**")
                                en_nome = st.text_input("Nome", value=dados_cliente_sel['nome'])
                                en_doc = st.text_input("CPF/CNPJ", value=dados_cliente_sel['documento'])
                                en_tel = st.text_input("Telefone", value=dados_cliente_sel['telefone'])
                                if st.form_submit_button("💾 Salvar Alterações"):
                                    execute_query("UPDATE clientes SET nome=%s, documento=%s, telefone=%s WHERE id=%s", (en_nome, en_doc, en_tel, id_c_sel))
                                    registrar_auditoria("Edição", "Clientes", f"Dados cadastrais do cliente ID {id_c_sel} atualizados.")
                                    st.session_state.flash_msg = "Atualizado com sucesso!"
                                    st.session_state.reset_keys['edit_cli'] += 1
                                    st.rerun()
                                    
                        elif acao_clientes == "Excluir":
                            st.warning("Atenção: Excluir o cliente removerá o cadastro e todos os veículos vinculados a ele.")
                            if st.button("🗑️ Excluir Cliente e Frotas", key=f"btn_excluir_cli_{id_c_sel}"):
                                execute_query("DELETE FROM veiculos WHERE cliente_id=%s", (id_c_sel,))
                                execute_query("DELETE FROM clientes WHERE id=%s", (id_c_sel,))
                                registrar_auditoria("Exclusão", "Clientes", f"Cliente ID {id_c_sel} e frotas excluídos.")
                                st.session_state.flash_msg = "Cliente excluído com sucesso!"
                                st.session_state["termo_cli_ativo"] = ""
                                st.session_state.reset_keys['edit_cli'] += 1
                                st.rerun()
                else:
                    st.warning("Nenhum cliente encontrado.")
    tab_idx += 1

    # --- ABA: RELATÓRIOS ---
    with tabs[tab_idx]:
        st.header("📖 Relatórios Operacionais")
        
        if st.session_state.is_admin:
            servico_atual = "Ambos (Furto/Roubo + Monitoramento)"
        else:
            res_servico = fetch_data("SELECT servicos FROM empresas WHERE nome=%s", (st.session_state.nome_empresa,))
            if res_servico and 'servicos' in res_servico[0] and res_servico[0]['servicos']:
                servico_atual = res_servico[0]['servicos']
            else:
                servico_atual = "Ambos (Furto/Roubo + Monitoramento)"
        
        mostrar_fr = "Furto e Roubo" in servico_atual or "Ambos" in servico_atual
        mostrar_mon = "Monitoramento" in servico_atual or "Ambos" in servico_atual
        
        abas_relatorios_ativas = []
        if mostrar_fr: abas_relatorios_ativas.append("🚨 Relatórios de Furto e Roubo")
        if mostrar_mon: abas_relatorios_ativas.append("📡 Relatórios de Monitoramento Técnico")
        
        if not abas_relatorios_ativas:
            st.warning("Nenhum serviço de relatório atrelado a esta empresa.")
        else:
            sub_tabs = st.tabs(abas_relatorios_ativas)
            idx_sub = 0
            
            if mostrar_fr:
                with sub_tabs[idx_sub]:
                    st.subheader("Controle de Ocorrências de Furto e Roubo")
                    col_f1, col_f2 = st.columns(2)
                    b_fr = col_f1.text_input("🔍 Buscar por Placa, Nome ou CPF (Furto/Roubo)", key="b_fr")
                    p_fr = col_f2.text_input("📅 Filtrar por Data (Furto/Roubo)", key="p_fr")
                    
                    q_fr = "SELECT * FROM historico WHERE tipo IN ('Furto', 'Roubo')"
                    p_list_fr = []
                    if not st.session_state.is_admin:
                        q_fr += " AND empresa=%s"
                        p_list_fr.append(st.session_state.nome_empresa)
                    if b_fr:
                        q_fr += " AND (lower(cliente) LIKE %s OR lower(placa) LIKE %s)"
                        p_list_fr.extend([f"%{b_fr.lower()}%", f"%{b_fr.lower()}%"])
                    if p_fr:
                        q_fr += " AND data_hora LIKE %s"
                        p_list_fr.append(f"%{p_fr}%")
                    q_fr += " ORDER BY id DESC"
                    
                    res_fr = fetch_data(q_fr, tuple(p_list_fr))
                    
                    if res_fr:
                        df_fr = pd.DataFrame(res_fr)
                        st.dataframe(df_fr[['id', 'data_hora', 'cliente', 'placa', 'tipo', 'status']], use_container_width=True)
                        
                        st.markdown("### 🔎 Ficha e Finalização de Ocorrência")
                        lista_sel_fr = [""] + [f"{h['id']} - {h['placa']} ({h['tipo']} - {h['status']})" for h in res_fr]
                        
                        k_rel_fr = st.session_state.reset_keys['rel_fr']
                        reg_sel_fr = st.selectbox("Selecione um atendimento para visualizar ou finalizar:", lista_sel_fr, key=f"sb_rel_fr_{k_rel_fr}")
                        
                        if reg_sel_fr != "":
                            id_r = int(reg_sel_fr.split(" - ")[0])
                            dados_fr = next(item for item in res_fr if item["id"] == id_r)
                            
                            col_b1, col_b2 = st.columns([1, 4])
                            with col_b1:
                                if st.button("❌ Fechar Ficha", key="fechar_fr_btn"):
                                    st.session_state.reset_keys['rel_fr'] += 1
                                    st.rerun()
                            if st.session_state.is_admin:
                                with col_b2:
                                    if st.button("🗑️ Excluir este Relatório de Ocorrência", key=f"del_rel_fr_{id_r}"):
                                        execute_query("DELETE FROM historico WHERE id=%s", (id_r,))
                                        registrar_auditoria("Exclusão", "Relatórios", f"Relatório de Ocorrência ID {id_r} excluído pelo administrador.")
                                        st.session_state.flash_msg = "Relatório excluído com sucesso!"
                                        st.session_state.reset_keys['rel_fr'] += 1
                                        st.rerun()

                            st.markdown(f'''
                            <div class="ficha-box">
                                <h4 style="color:#8b0000; text-align:center;">Ficha de Ocorrência nº {dados_fr['id']} ({dados_fr['tipo']})</h4>
                                <hr>
                                <p><b>Data/Hora de Abertura:</b> {dados_fr['data_hora']}</p>
                                <p><b>Cliente:</b> {dados_fr['cliente']}</p>
                                <p><b>Placa:</b> {dados_fr['placa']}</p>
                                <p><b>Status Atual:</b> <b>{dados_fr['status']}</b></p>
                                <hr>
                                <p><b>Detalhes / Dinâmica:</b></p>
                                <p>{dados_fr['detalhes']}</p>
                            </div>
                            ''', unsafe_allow_html=True)
                            
                            if dados_fr['status'] == 'EM ANDAMENTO':
                                st.markdown("---")
                                with st.form(f"form_finalizar_reg_{id_r}", clear_on_submit=True):
                                    st.write("🟢 **Finalizar Atendimento:**")
                                    desfecho = st.text_area("Informe o desfecho do caso (ex: Veículo recuperado com sucesso)")
                                    if st.form_submit_button("✅ Concluir e Finalizar Ocorrência"):
                                        novo_detalhe = dados_fr['detalhes'] + f" | DESFECHO: {desfecho}"
                                        execute_query("UPDATE historico SET status='FINALIZADO', detalhes=%s WHERE id=%s", (novo_detalhe, id_r))
                                        registrar_auditoria("Finalização", "Operação", f"Ocorrência ID {id_r} finalizada.")
                                        st.session_state.flash_msg = "Ocorrência finalizada com sucesso!"
                                        st.session_state.reset_keys['rel_fr'] += 1
                                        st.rerun()
                            
                            st.markdown("<br>", unsafe_allow_html=True)
                            st.markdown(gerar_relatorio_html(dados_fr, st.session_state.nome_empresa), unsafe_allow_html=True)
                    else:
                        st.info("Nenhum registro de Furto ou Roubo encontrado.")
                idx_sub += 1

            if mostrar_mon:
                with sub_tabs[idx_sub]:
                    st.subheader("Eventos de Monitoramento Técnico")
                    col_m1, col_m2 = st.columns(2)
                    b_mon = col_m1.text_input("🔍 Buscar por Placa, Nome ou CPF (Monitoramento)", key="b_mon")
                    p_mon = col_m2.text_input("📅 Filtrar por Data (Monitoramento)", key="p_mon")
                    
                    q_mon = "SELECT * FROM historico WHERE tipo='Monitoramento'"
                    p_list_mon = []
                    if not st.session_state.is_admin:
                        q_mon += " AND empresa=%s"
                        p_list_mon.append(st.session_state.nome_empresa)
                    if b_mon:
                        q_mon += " AND (lower(cliente) LIKE %s OR lower(placa) LIKE %s)"
                        p_list_mon.extend([f"%{b_mon.lower()}%", f"%{b_mon.lower()}%"])
                    if p_mon:
                        q_mon += " AND data_hora LIKE %s"
                        p_list_mon.append(f"%{p_mon}%")
                    q_mon += " ORDER BY id DESC"
                    
                    res_mon = fetch_data(q_mon, tuple(p_list_mon))
                    
                    if res_mon:
                        df_mon = pd.DataFrame(res_mon)
                        st.dataframe(df_mon[['id', 'data_hora', 'cliente', 'placa', 'tipo', 'status']], use_container_width=True)
                        
                        st.markdown("### 🔎 Ficha de Monitoramento")
                        lista_sel_mon = [""] + [f"{h['id']} - {h['placa']} ({h['data_hora']})" for h in res_mon]
                        
                        k_rel_mon = st.session_state.reset_keys['rel_mon']
                        reg_sel_mon = st.selectbox("Selecione um registro para visualizar:", lista_sel_mon, key=f"sb_rel_mon_{k_rel_mon}")
                        
                        if reg_sel_mon != "":
                            id_m = int(reg_sel_mon.split(" - ")[0])
                            dados_mon = next(item for item in res_mon if item["id"] == id_m)
                            
                            col_mb1, col_mb2 = st.columns([1, 4])
                            with col_mb1:
                                if st.button("❌ Fechar Ficha", key="fechar_mon_btn"):
                                    st.session_state.reset_keys['rel_mon'] += 1
                                    st.rerun()
                            if st.session_state.is_admin:
                                with col_mb2:
                                    if st.button("🗑️ Excluir este Relatório de Monitoramento", key=f"del_rel_mon_{id_m}"):
                                        execute_query("DELETE FROM historico WHERE id=%s", (id_m,))
                                        registrar_auditoria("Exclusão", "Relatórios", f"Relatório de Monitoramento ID {id_m} excluído pelo administrador.")
                                        st.session_state.flash_msg = "Relatório excluído com sucesso!"
                                        st.session_state.reset_keys['rel_mon'] += 1
                                        st.rerun()

                            st.markdown(f'''
                            <div class="ficha-box">
                                <h4 style="color:#4a0e4e; text-align:center;">Ficha de Monitoramento nº {dados_mon['id']}</h4>
                                <hr>
                                <p><b>Data/Hora:</b> {dados_mon['data_hora']}</p>
                                <p><b>Cliente:</b> {dados_mon['cliente']}</p>
                                <p><b>Placa:</b> {dados_mon['placa']}</p>
                                <p><b>Status:</b> {dados_mon['status']}</p>
                                <hr>
                                <p><b>Detalhes / Ação da Central:</b></p>
                                <p>{dados_mon['detalhes']}</p>
                            </div>
                            ''', unsafe_allow_html=True)
                            
                            st.markdown("<br>", unsafe_allow_html=True)
                            st.markdown(gerar_relatorio_html(dados_mon, st.session_state.nome_empresa), unsafe_allow_html=True)
                    else:
                        st.info("Nenhum registro de monitoramento encontrado.")
                idx_sub += 1

    tab_idx += 1

    # --- ABA: MEU FATURAMENTO (EXCLUSIVO PARA EMPRESAS PARCEIRAS) ---
    if not st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("💰 Meu Faturamento e Frotas Ativas")
            
            res_emp_info = fetch_data("SELECT servicos, valor_veiculo, dia_vencimento, status_pagamento, valor_pago FROM empresas WHERE nome=%s", (st.session_state.nome_empresa,))
            servico_emp = res_emp_info[0]['servicos'] if res_emp_info else "Ambos"
            valor_por_veiculo = res_emp_info[0]['valor_veiculo'] if (res_emp_info and res_emp_info[0]['valor_veiculo'] is not None) else 3.00
            dia_venc = res_emp_info[0]['dia_vencimento'] if (res_emp_info and res_emp_info[0]['dia_vencimento'] is not None) else 10
            status_pag = res_emp_info[0]['status_pagamento'] if (res_emp_info and res_emp_info[0]['status_pagamento'] is not None) else "Pendente"
            valor_pago_efetivo = res_emp_info[0]['valor_pago'] if (res_emp_info and res_emp_info[0]['valor_pago'] is not None) else 0.00
            
            status_visual = calcular_status_fatura(status_pag, dia_venc)

            if status_visual == "🔴 Vencida / Atrasada":
                st.error("⚠️ **AVISO FINANCEIRO IMPORTANTE - FATURA ATRASADA:** Identificamos que sua fatura venceu e encontra-se em atraso. Seus serviços encontram-se temporariamente **interrompidos até a quitação do débito**. Por favor, regularize sua situação com o suporte financeiro da Central para o restabelecimento imediato das operações.")
            elif status_visual == "🟠 Vence Hoje":
                st.warning("⚠️ **AVISO FINANCEIRO:** Sua fatura referente ao fechamento do último dia do mês **vence hoje**. Evite transtornos e o bloqueio dos serviços realizando o pagamento.")
            elif status_visual == "🟡 Fatura Fechada (Próxima ao Vencimento)":
                st.info(f"🔔 **Aviso Financeiro Importante:** Sua fatura foi fechada (corte de 2 dias antes do vencimento dia {dia_venc}). Fique atento para manter seus serviços ativos.")
            else:
                st.success("✅ **Situação Financeira Regularizada:** Suas faturas encontram-se em dia. Obrigado por manter sua parceria conosco!")

            st.info(f"ℹ️ **Seu Pacote Contratado:** {servico_emp} | **Valor Unitário:** R$ {valor_por_veiculo:.2f} | **Vencimento:** Todo dia {dia_venc} do mês (Fechamento 2 dias antes)")
            
            q_conta_veic = """
                SELECT count(v.id) as total_veiculos 
                FROM veiculos v 
                JOIN clientes c ON v.cliente_id = c.id 
                WHERE c.empresa = %s AND c.status = 'Ativo'
            """
            res_conta = fetch_data(q_conta_veic, (st.session_state.nome_empresa,))
            total_veiculos = res_conta[0]['total_veiculos'] if res_conta else 0
            
            valor_total_fatura = total_veiculos * valor_por_veiculo
            
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("🚗 Total de Veículos Ativos", f"{total_veiculos}")
            col_m2.metric("💵 Valor Unitário Aplicado", f"R$ {valor_por_veiculo:.2f}")
            col_m3.metric("💳 Fatura Calculada", f"R$ {valor_total_fatura:.2f}", delta=f"Vencimento dia {dia_venc}", delta_color="off")
            col_m4.metric("📌 Status da Fatura", f"{status_visual}")

            if status_pag == "Pago":
                st.info(f"💡 **Valor Quitado Registrado:** R$ {valor_pago_efetivo:.2f} (Com juros/acréscimos aplicados, se houver).")
            
            st.markdown("---")
            st.subheader("🔍 Consulta de Faturas Anteriores por Mês")
            mes_busca_parceiro = st.text_input("Digite o Mês/Ano de referência (Ex: 06/2026 ou 07/2026):", value="")
            if mes_busca_parceiro:
                res_hist_p = fetch_data("SELECT * FROM historico_faturas WHERE empresa=%s AND mes_ref=%s", (st.session_state.nome_empresa, mes_busca_parceiro))
                if res_hist_p:
                    df_hp = pd.DataFrame(res_hist_p)[['mes_ref', 'total_veiculos', 'valor_unitario', 'valor_pago', 'status', 'data_pagamento']]
                    df_hp.columns = ['Mês Ref.', 'Veículos', 'Valor Unit.', 'Valor Pago', 'Status', 'Data Pgto']
                    st.dataframe(df_hp, use_container_width=True)
                else:
                    st.info(f"Nenhum registro de fatura encontrado para o mês {mes_busca_parceiro}.")

            st.markdown("---")
            st.subheader("📋 Detalhamento da Frota Faturada Atual")
            
            q_detalhe_frota = """
                SELECT c.nome as cliente, c.documento, v.tipo_veic, v.placa, v.modelo, v.cor 
                FROM veiculos v 
                JOIN clientes c ON v.cliente_id = c.id 
                WHERE c.empresa = %s AND c.status = 'Ativo'
            """
            res_frota = fetch_data(q_detalhe_frota, (st.session_state.nome_empresa,))
            
            if res_frota:
                df_frota_parceiro = pd.DataFrame(res_frota)
                df_frota_parceiro.columns = ['Cliente', 'CPF/CNPJ', 'Tipo', 'Placa', 'Modelo', 'Cor']
                st.dataframe(df_frota_parceiro, use_container_width=True)
            else:
                st.info("Nenhum veículo ativo registrado em sua base no momento.")
                
        tab_idx += 1

    # --- ABA: PARCEIROS (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🏢 Gerenciamento de Empresas Parceiras e Precificação")
            
            acao_parceiros = st.radio("Ação Empresas:", ["Listar", "Incluir Nova", "Editar", "Excluir"], horizontal=True)
            st.markdown("---")
            
            empresas_res = fetch_data("SELECT id, nome, cnpj, endereco, telefone, responsavel, servicos, valor_veiculo, dia_vencimento, status_pagamento, valor_pago FROM empresas")
            df_empresas = pd.DataFrame(empresas_res) if empresas_res else pd.DataFrame()
            
            if acao_parceiros == "Listar":
                if not df_empresas.empty:
                    for _, emp in df_empresas.iterrows():
                        with st.expander(f"📁 Empresa: {emp['nome']}"):
                            st.write(f"**CNPJ/Senha:** {emp['cnpj']} | **Responsável:** {emp['responsavel']}")
                            st.write(f"**Telefone:** {emp['telefone']} | **Endereço:** {emp['endereco']}")
                            servico_vinculado = emp['servicos'] if 'servicos' in emp and emp['servicos'] else "Ambos (Furto/Roubo + Monitoramento)"
                            valor_unit = emp['valor_veiculo'] if ('valor_veiculo' in emp and emp['valor_veiculo'] is not None) else 3.00
                            dia_v = emp['dia_vencimento'] if ('dia_vencimento' in emp and emp['dia_vencimento'] is not None) else 10
                            stat_pag = emp['status_pagamento'] if ('status_pagamento' in emp and emp['status_pagamento'] is not None) else "Pendente"
                            val_pago_ef = emp['valor_pago'] if ('valor_pago' in emp and emp['valor_pago'] is not None) else 0.00
                            
                            st.write(f"**Pacote:** {servico_vinculado} | **Preço/Veículo:** R$ {valor_unit:.2f} | **Vencimento:** Dia {dia_v}")
                            st.write(f"**Status Fatura:** {stat_pag} | **Valor Pago Registrado:** R$ {val_pago_ef:.2f}")
                else:
                    st.info("Nenhuma empresa parceira cadastrada.")
            
            elif acao_parceiros == "Incluir Nova":
                with st.form("nova_empresa", clear_on_submit=True):
                    e_nome = st.text_input("Nome da Empresa (Será o Login) *")
                    e_cnpj = st.text_input("CNPJ (Será a Senha) *")
                    e_end = st.text_input("Endereço")
                    e_tel = st.text_input("Telefone")
                    e_resp = st.text_input("Responsável")
                    e_servicos = st.selectbox("Serviços Contratados", ["Ambos (Furto/Roubo + Monitoramento)", "Apenas Furto e Roubo", "Apenas Monitoramento"])
                    e_valor = st.number_input("Valor por Veículo (R$) *", min_value=0.0, value=3.00, format="%.2f")
                    e_venc = st.number_input("Dia de Vencimento da Fatura *", min_value=1, max_value=31, value=10)
                    
                    if st.form_submit_button("Registrar Parceiro"):
                        if e_nome and e_cnpj:
                            execute_query("INSERT INTO empresas (nome, cnpj, endereco, telefone, responsavel, servicos, valor_veiculo, dia_vencimento, status_pagamento, valor_pago) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", 
                                          (e_nome, e_cnpj, e_end, e_tel, e_resp, e_servicos, e_valor, e_venc, 'Pendente', 0.00))
                            registrar_auditoria("Cadastro", "Parceiros", f"Empresa {e_nome} criada. Pacote: {e_servicos} | R$ {e_valor:.2f} | Venc. Dia {e_venc}.")
                            st.session_state.flash_msg = "Empresa cadastrada com sucesso e tela limpa!"
                            st.rerun()
                        else:
                            st.error("Nome e CNPJ são obrigatórios.")
                            
            elif acao_parceiros in ["Editar", "Excluir"]:
                if empresas_res:
                    lista_opcoes_e = [f"{e['id']} - {e['nome']}" for e in empresas_res]
                    
                    k_edit_emp = st.session_state.reset_keys['edit_emp']
                    emp_selecionada = st.selectbox("🔍 Selecione a Empresa na lista (ou digite para buscar):", [""] + lista_opcoes_e, key=f"sb_edit_emp_{k_edit_emp}")
                    
                    if emp_selecionada:
                        if st.button("❌ Fechar Seleção", key="btn_close_edit_emp"):
                            st.session_state.reset_keys['edit_emp'] += 1
                            st.rerun()

                        id_emp = int(emp_selecionada.split(" - ")[0])
                        dados_e = next(item for item in empresas_res if item["id"] == id_emp)
                        
                        if acao_parceiros == "Editar":
                            with st.form(f"form_edit_emp", clear_on_submit=True):
                                ne_nome = st.text_input("Nome", value=dados_e['nome'])
                                ne_resp = st.text_input("Responsável", value=dados_e['responsavel'])
                                ne_tel = st.text_input("Telefone", value=dados_e['telefone'])
                                ne_end = st.text_input("Endereço", value=dados_e['endereco'])
                                
                                serv_atual = dados_e['servicos'] if 'servicos' in dados_e and dados_e['servicos'] else "Ambos (Furto/Roubo + Monitoramento)"
                                opcoes_s = ["Ambos (Furto/Roubo + Monitoramento)", "Apenas Furto e Roubo", "Apenas Monitoramento"]
                                idx_serv = opcoes_s.index(serv_atual) if serv_atual in opcoes_s else 0
                                ne_servicos = st.selectbox("Serviços Contratados", opcoes_s, index=idx_serv)

                                val_atual = dados_e['valor_veiculo'] if ('valor_veiculo' in dados_e and dados_e['valor_veiculo'] is not None) else 3.00
                                ne_valor = st.number_input("Valor por Veículo (R$)", min_value=0.0, value=float(val_atual), format="%.2f")

                                venc_atual = dados_e['dia_vencimento'] if ('dia_vencimento' in dados_e and dados_e['dia_vencimento'] is not None) else 10
                                ne_venc = st.number_input("Dia de Vencimento da Fatura", min_value=1, max_value=31, value=int(venc_atual))

                                if st.form_submit_button("💾 Salvar Alterações"):
                                    execute_query("UPDATE empresas SET nome=%s, responsavel=%s, telefone=%s, endereco=%s, servicos=%s, valor_veiculo=%s, dia_vencimento=%s WHERE id=%s", 
                                                  (ne_nome, ne_resp, ne_tel, ne_end, ne_servicos, ne_valor, ne_venc, id_emp))
                                    registrar_auditoria("Edição", "Parceiros", f"Parceiro ID {id_emp} alterado. Preço: R$ {ne_valor:.2f} | Venc. Dia {ne_venc}")
                                    st.session_state.flash_msg = "Alterações salvas com sucesso!"
                                    st.session_state.reset_keys['edit_emp'] += 1
                                    st.rerun()
                        
                        elif acao_parceiros == "Excluir":
                            st.warning(f"Tem certeza que deseja excluir a empresa **{dados_e['nome']}**?")
                            if st.button("🗑️ Excluir Parceiro"):
                                execute_query("DELETE FROM empresas WHERE id=%s", (id_emp,))
                                registrar_auditoria("Exclusão", "Parceiros", f"Parceiro ID {id_emp} excluído.")
                                st.session_state.flash_msg = "Empresa excluída com sucesso!"
                                st.session_state.reset_keys['edit_emp'] += 1
                                st.rerun()
                else:
                    st.warning("Nenhuma empresa encontrada.")
        tab_idx += 1

    # --- ABA: FINANCEIRO (SÓ ADMIN COM PAINEL DE RESUMO EXECUTIVO E EDIÇÃO DIRETA) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("💰 Controle Financeiro Global de Parceiros")
            st.info("ℹ️ Painel executivo financeiro com o resumo consolidado a receber, valores atrasados e valores quitados de todos os parceiros.")
            
            empresas_cad = fetch_data("SELECT id, nome, valor_veiculo, dia_vencimento, status_pagamento, valor_pago FROM empresas")
            
            total_a_receber = 0.0
            total_atrasado = 0.0
            total_pago = 0.0
            
            dados_financeiro_global = []
            if empresas_cad:
                for emp in empresas_cad:
                    nome_emp = emp['nome']
                    val_unit = emp['valor_veiculo'] if emp['valor_veiculo'] is not None else 3.00
                    dia_v = emp['dia_vencimento'] if emp['dia_vencimento'] is not None else 10
                    stat_p = emp['status_pagamento'] if emp['status_pagamento'] is not None else "Pendente"
                    v_pago_ef = emp['valor_pago'] if emp['valor_pago'] is not None else 0.00
                    
                    status_calculado = calcular_status_fatura(stat_p, dia_v)
                    
                    q_v = "SELECT count(v.id) as qtd FROM veiculos v JOIN clientes c ON v.cliente_id = c.id WHERE c.empresa = %s AND c.status = 'Ativo'"
                    res_v = fetch_data(q_v, (nome_emp,))
                    qtd_v = res_v[0]['qtd'] if res_v else 0
                    valor_calc = qtd_v * val_unit
                    
                    if "Pago" in status_calculado:
                        total_pago += v_pago_ef if v_pago_ef > 0 else valor_calc
                    elif "Vencida / Atrasada" in status_calculado or "Vence Hoje" in status_calculado:
                        total_atrasado += valor_calc
                    else:
                        total_a_receber += valor_calc
                    
                    dados_financeiro_global.append({
                        "Empresa Parceira": nome_emp,
                        "Veículos Ativos": qtd_v,
                        "Valor Unitário": f"R$ {val_unit:.2f}",
                        "Vencimento": f"Dia {dia_v}",
                        "Faturamento Estimado": f"R$ {valor_calc:.2f}",
                        "Valor Pago Registrado": f"R$ {v_pago_ef:.2f}",
                        "Status": status_calculado
                    })
            
            col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
            col_kpi1.metric("💵 Valor a Receber (Em Dias / Próximos)", f"R$ {total_a_receber:.2f}")
            col_kpi2.metric("🔴 Valor Atrasado / Vencido", f"R$ {total_atrasado:.2f}", delta_color="inverse")
            col_kpi3.metric("🟢 Valor Pago (Quitado)", f"R$ {total_pago:.2f}")
            
            st.markdown("---")
            
            if empresas_cad:
                df_fin_global = pd.DataFrame(dados_financeiro_global)
                st.dataframe(df_fin_global, use_container_width=True)
                
                st.markdown("---")
                st.subheader("🔍 Consulta Histórica de Faturas por Mês (Busca Inteligente)")
                col_h1, col_h2 = st.columns(2)
                mes_busca_admin = col_h1.text_input("Filtrar por Mês/Ano (Ex: 06/2026):", value="")
                emp_busca_admin = col_h2.selectbox("Filtrar por Empresa:", ["Todas"] + [e['nome'] for e in empresas_cad])

                q_hist_adm = "SELECT * FROM historico_faturas WHERE 1=1"
                p_hist_adm = []
                if mes_busca_admin:
                    q_hist_adm += " AND mes_ref = %s"
                    p_hist_adm.append(mes_busca_admin)
                if emp_busca_admin != "Todas":
                    q_hist_adm += " AND empresa = %s"
                    p_hist_adm.append(emp_busca_admin)
                
                res_hist_adm = fetch_data(q_hist_adm, tuple(p_hist_adm))
                if res_hist_adm:
                    df_hadm = pd.DataFrame(res_hist_adm)[['mes_ref', 'empresa', 'total_veiculos', 'valor_unitario', 'valor_pago', 'status', 'data_pagamento']]
                    df_hadm.columns = ['Mês Ref.', 'Empresa', 'Veículos', 'Valor Unit.', 'Valor Pago', 'Status', 'Data Pgto']
                    st.dataframe(df_hadm, use_container_width=True)
                else:
                    st.info("Nenhum histórico de fatura encontrado para os filtros selecionados.")

                st.markdown("---")
                st.subheader("⚡ Atualizar Pagamento e Valor da Fatura (Com Juros/Acréscimos)")
                
                if 'k_fin' not in st.session_state:
                    st.session_state.k_fin = 0
                
                lista_p_nomes = [e['nome'] for e in empresas_cad]
                emp_escolhida_pagto = st.selectbox("Selecione a Empresa Parceira:", [""] + lista_p_nomes, key=f"sel_fin_emp_{st.session_state.k_fin}")
                
                if emp_escolhida_pagto != "":
                    if st.button("❌ Cancelar / Limpar Seleção", key="btn_close_fin"):
                        st.session_state.k_fin += 1
                        st.rerun()
                        
                    dados_emp_fin = next(item for item in empresas_cad if item["nome"] == emp_escolhida_pagto)
                    val_atual = dados_emp_fin['valor_veiculo'] if dados_emp_fin['valor_veiculo'] is not None else 3.00
                    stat_atual = dados_emp_fin['status_pagamento'] if dados_emp_fin['status_pagamento'] is not None else "Pendente"
                    vp_atual = dados_emp_fin['valor_pago'] if dados_emp_fin['valor_pago'] is not None else 0.00
                    
                    q_v_calc = "SELECT count(v.id) as qtd FROM veiculos v JOIN clientes c ON v.cliente_id = c.id WHERE c.empresa = %s AND c.status = 'Ativo'"
                    res_v_calc = fetch_data(q_v_calc, (emp_escolhida_pagto,))
                    qtd_v_calc = res_v_calc[0]['qtd'] if res_v_calc else 0
                    sugestao_total = qtd_v_calc * val_atual
                    if vp_atual == 0.0:
                        vp_atual = sugestao_total

                    with st.form("form_atualiza_status_pagto", clear_on_submit=True):
                        st.write(f"**Empresa Selecionada:** {emp_escolhida_pagto}")
                        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                        
                        novo_valor_unit = col_f1.number_input("Novo Valor Unitário:", min_value=0.0, value=float(val_atual), format="%.2f")
                        novo_valor_pago = col_f2.number_input("Valor Total Pago:", min_value=0.0, value=float(vp_atual), format="%.2f")
                        mes_referencia = col_f3.text_input("Mês Ref. (Ex: 06/2026):", value=datetime.now().strftime("%m/%Y"))
                        
                        opcoes_st_fin = ["Pendente", "Pago"]
                        idx_st_fin = opcoes_st_fin.index(stat_atual) if stat_atual in opcoes_st_fin else 0
                        novo_status_pagto = col_f4.selectbox("Status:", opcoes_st_fin, index=idx_st_fin)
                        
                        if st.form_submit_button("💾 Salvar Pagamento e Registrar Histórico"):
                            execute_query("UPDATE empresas SET status_pagamento=%s, valor_veiculo=%s, valor_pago=%s WHERE nome=%s", (novo_status_pagto, novo_valor_unit, novo_valor_pago, emp_escolhida_pagto))
                            
                            # Salva também no histórico mensal para a busca inteligente
                            data_pgto_hoje = get_horario_brasil_str()
                            execute_query("INSERT INTO historico_faturas (mes_ref, empresa, total_veiculos, valor_unitario, valor_pago, status, data_pagamento) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                          (mes_referencia, emp_escolhida_pagto, qtd_v_calc, novo_valor_unit, novo_valor_pago, novo_status_pagto, data_pgto_hoje))

                            registrar_auditoria("Financeiro", "Faturamento", f"Fatura de {emp_escolhida_pagto} (Mês {mes_referencia}) alterada para {novo_status_pagto} | Valor Pago: R$ {novo_valor_pago:.2f}")
                            st.session_state.flash_msg = f"Financeiro e Histórico de {emp_escolhida_pagto} atualizados com sucesso!"
                            st.session_state.k_fin += 1
                            st.rerun()
            else:
                st.info("Nenhuma empresa parceira cadastrada para faturamento.")
        tab_idx += 1

    # --- AUDITORIA ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🕵️ Auditoria e Rastreabilidade")
            mes_atual_padrao = datetime.now().strftime("%m/%Y")
            filtro_mes_aud = st.text_input("🔍 Filtrar por Mês/Ano", value=mes_atual_padrao)
            
            q_aud = "SELECT * FROM auditoria"
            p_aud = []
            if filtro_mes_aud:
                q_aud += " WHERE data_hora LIKE %s"
                p_aud.append(f"%{filtro_mes_aud}%")
            q_aud += " ORDER BY id DESC"
            
            res_aud = fetch_data(q_aud, tuple(p_aud))
            
            if res_aud:
                df_auditoria = pd.DataFrame(res_aud)
                if 'usuario' in df_auditoria.columns and 'detalhes' in df_auditoria.columns:
                    colunas_ordem = ['id', 'data_hora', 'usuario', 'acao', 'modulo', 'detalhes']
                    colunas_existentes = [c for c in colunas_ordem if c in df_auditoria.columns]
                    df_auditoria = df_auditoria[colunas_existentes]
                    df_auditoria.columns = ['ID', 'Data/Hora', 'Empresa / Usuário', 'Ação', 'Módulo', 'Detalhes']

                st.dataframe(df_auditoria, use_container_width=True)
                
                st.markdown("### 🗑️ Excluir Registro Específico de Auditoria")
                lista_aud = [""] + [f"{row['ID']} - {row['Data/Hora']} ({row['Empresa / Usuário']} - {row['Ação']} / {row['Módulo']})" for _, row in df_auditoria.iterrows()]
                
                k_aud_del = st.session_state.reset_keys['aud_del']
                aud_sel_excluir = st.selectbox("Selecione o registro de auditoria que deseja excluir:", lista_aud, key=f"sb_aud_del_{k_aud_del}")
                
                if aud_sel_excluir != "":
                    if st.button("❌ Fechar Seleção", key="btn_close_edit_emp"):
                        st.session_state.reset_keys['aud_del'] += 1
                        st.rerun()
                        
                    id_aud_del = int(aud_sel_excluir.split(" - ")[0])
                    if st.button("🗑️ Excluir Registro de Auditoria Selecionado", key=f"btn_del_aud_{id_aud_del}"):
                        execute_query("DELETE FROM auditoria WHERE id=%s", (id_aud_del,))
                        st.session_state.flash_msg = f"Registro de auditoria ID {id_aud_del} excluído com sucesso!"
                        st.session_state.reset_keys['aud_del'] += 1
                        st.rerun()
            else:
                st.info(f"Nenhum registro de auditoria para '{filtro_mes_aud}'.")
