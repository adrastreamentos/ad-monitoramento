import streamlit as st
import sqlite3
from datetime import datetime
import urllib.parse

# --- CONFIGURAÇÕES DA PÁGINA E IDENTIDADE VISUAL ---
st.set_page_config(page_title="AD Rastreamento Veicular", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    /* Identidade AD Rastreamento: Roxo e Vermelho Escuro */
    .stApp { background-color: #fdfdfd; }
    h1, h2, h3 { color: #4a0e4e; } /* Roxo */
    .stButton>button { background-color: #8b0000; color: white; font-weight: bold; border-radius: 6px; border: none; }
    .stButton>button:hover { background-color: #4a0e4e; color: white; }
    div[data-testid="stSidebar"] { background-color: #4a0e4e; }
    div[data-testid="stSidebar"] * { color: white; }
</style>
""", unsafe_allow_html=True)

# --- BANCO DE DADOS NATIVO (Sem dependências externas) ---
DB_PATH = "ad_monitoramento.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS empresas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, cnpj TEXT, endereco TEXT, telefone TEXT, responsavel TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, documento TEXT, endereco TEXT, telefone TEXT, tipo_veic TEXT, placa TEXT, modelo TEXT, cor TEXT, empresa TEXT, status TEXT DEFAULT 'Ativo', ultima_atualizacao TEXT DEFAULT '')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS historico (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, cliente TEXT, placa TEXT, tipo TEXT, status TEXT, detalhes TEXT, empresa TEXT)''')
    conn.commit()
    conn.close()

init_db()

def fetch_data(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    data = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return data

def execute_query(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()

# --- CONTROLE DE SESSÃO ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.is_admin = False
    st.session_state.nome_empresa = ""

# ==========================================
# 1. TELA DE LOGIN
# ==========================================
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>🛡️ AD Rastreamento Veicular</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #8b0000; font-weight: bold;'>Central de Operações e Apoio às Motoristas</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            user = st.text_input("Usuário ou Nome da Empresa")
            senha = st.text_input("Senha ou CNPJ", type="password")
            submit = st.form_submit_button("Entrar no Sistema")
            
            if submit:
                if user == "AD" and senha == "admin":
                    st.session_state.logged_in = True
                    st.session_state.is_admin = True
                    st.session_state.nome_empresa = "AD RASTREAMENTO VEICULAR"
                    st.rerun()
                else:
                    res = fetch_data("SELECT nome FROM empresas WHERE nome=? AND cnpj=?", (user, senha))
                    if res:
                        st.session_state.logged_in = True
                        st.session_state.is_admin = False
                        st.session_state.nome_empresa = res[0]['nome']
                        st.rerun()
                    else:
                        st.error("Acesso Negado: Login ou Senha incorretos.")

# ==========================================
# 2. SISTEMA PRINCIPAL
# ==========================================
else:
    with st.sidebar:
        st.write(f"👤 **Conectado como:** {st.session_state.nome_empresa}")
        if st.button("🚪 Sair do Sistema"):
            st.session_state.logged_in = False
            st.rerun()
        st.markdown("---")
        st.markdown("Prioridade no suporte, segurança e agilidade para a frota feminina e nossos parceiros.")

    abas = ["👤 Clientes e Frotas", "📖 Histórico de Ocorrências"]
    if st.session_state.is_admin:
        abas.insert(0, "🚨 Operação 24h")
        abas.append("🏢 Gestão de Parceiros")
        
    tabs = st.tabs(abas)
    tab_idx = 0

    # --- MÓDULO: OPERAÇÃO 24H (SÓ ADMIN) ---
    if st.session_state.is_admin:
        with tabs[tab_idx]:
            st.header("🚨 Central de Operações e Ocorrências 24h")
            busca_op = st.text_input("🔍 Buscar veículo por Placa, CPF ou Nome")
            
            if busca_op and len(busca_op) >= 3:
                resultados = fetch_data(f"SELECT * FROM clientes WHERE status='Ativo' AND (lower(nome) LIKE '%{busca_op.lower()}%' OR lower(placa) LIKE '%{busca_op.lower()}%')")
                
                if resultados:
                    st.dataframe(resultados, use_container_width=True)
                    st.subheader("Registrar Atendimento")
                    
                    placas_disponiveis = [r['placa'] for r in resultados]
                    placa_sel = st.selectbox("Selecione a Placa:", placas_disponiveis)
                    
                    if placa_sel:
                        info_veic = next(item for item in resultados if item["placa"] == placa_sel)
                        
                        col_f, col_m = st.columns(2)
                        with col_f:
                            with st.form("form_furto"):
                                st.markdown("<h3 style='color: #8b0000;'>Abertura de Furto/Roubo</h3>", unsafe_allow_html=True)
                                tipo_ocorrencia = st.selectbox("Natureza", ["Furto", "Roubo"])
                                local_oc = st.text_input("Localização")
                                desc_oc = st.text_area("Descrição do Ocorrido")
                                status_oc = st.selectbox("Status", ["INICIADO", "EM ANDAMENTO", "FINALIZADO"])
                                
                                if st.form_submit_button("Salvar Ocorrência"):
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    detalhes = f"Local: {local_oc} | Desc: {desc_oc}"
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, tipo_ocorrencia, status_oc, detalhes, info_veic['empresa']))
                                    st.success(f"Ocorrência de {tipo_ocorrencia} registrada!")
                        
                        with col_m:
                            with st.form("form_monitoramento"):
                                st.markdown("<h3 style='color: #4a0e4e;'>Registro de Monitoramento</h3>", unsafe_allow_html=True)
                                evento_mon = st.selectbox("Evento", ["Cerca Virtual", "Desconexão de Bateria", "Falta de Comunicação", "Outros"])
                                acao_mon = st.text_area("Ação Realizada pela Central")
                                
                                if st.form_submit_button("Salvar Monitoramento"):
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    detalhes = f"Evento: {evento_mon} | Ação: {acao_mon}"
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, "Monitoramento", "FINALIZADO", detalhes, info_veic['empresa']))
                                    st.success("Evento de monitoramento salvo no histórico!")
                else:
                    st.warning("Nenhum veículo ativo encontrado.")
        tab_idx += 1

    # --- MÓDULO: CLIENTES E FROTAS ---
    with tabs[tab_idx]:
        st.header("👤 Gestão de Clientes e Frotas")
        with st.expander("➕ Cadastrar Novo Cliente/Veículo"):
            with st.form("novo_cliente"):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome do Cliente *")
                doc = c2.text_input("CPF/CNPJ")
                end = c1.text_input("Endereço")
                tel = c2.text_input("Telefone")
                emp = c1.selectbox("Empresa Parceira", [st.session_state.nome_empresa]) if not st.session_state.is_admin else c1.text_input("Empresa Parceira", value=st.session_state.nome_empresa)
                tipo = c2.selectbox("Tipo de Veículo", ["Carro", "Moto", "Caminhão", "Outro"])
                placa = c1.text_input("Placa *")
                mod = c2.text_input("Modelo")
                cor = c1.text_input("Cor")
                
                if st.form_submit_button("Salvar Ficha"):
                    if nome and placa:
                        agora = datetime.now().strftime('%d/%m/%Y %H:%M')
                        execute_query("INSERT INTO clientes (nome, documento, endereco, telefone, tipo_veic, placa, modelo, cor, empresa, status, ultima_atualizacao) VALUES (?,?,?,?,?,?,?,?,?,'Ativo',?)", 
                                  (nome, doc, end, tel, tipo, placa, mod, cor, emp, agora))
                        st.success("Cliente e veículo cadastrados com sucesso!")
                    else:
                        st.error("Nome e Placa são obrigatórios para o cadastro.")

        st.subheader("Base de Clientes")
        if st.session_state.is_admin:
            lista_clientes = fetch_data("SELECT id, nome, documento, telefone, placa, modelo, empresa, status FROM clientes")
        else:
            lista_clientes = fetch_data("SELECT id, nome, documento, telefone, placa, modelo, status FROM clientes WHERE empresa=?", (st.session_state.nome_empresa,))
        
        if lista_clientes:
            st.dataframe(lista_clientes, use_container_width=True)
        else:
            st.info("Nenhum cliente cadastrado ainda.")
        
        if not st.session_state.is_admin:
            st.markdown("### 🚑 Apoio da Central")
            texto_wpp = f"🚨 *ATENDIMENTO INDIRETO* 🚨\n\n🏢 Parceiro acionando: {st.session_state.nome_empresa}\n⚠️ O cliente entrou em contato direto. Precisamos de apoio na ocorrência!"
            url_wpp = f"https://wa.me/5584999305771?text={urllib.parse.quote(texto_wpp)}"
            st.markdown(f'<a href="{url_wpp}" target="_blank"><button style="background-color:#25D366; color:white; padding:10px; border-radius:5px; border:none; font-weight:bold;">🚨 Acionar Central AD via WhatsApp</button></a>', unsafe_allow_html=True)
    tab_idx += 1

    # --- MÓDULO: HISTÓRICO ---
    with tabs[tab_idx]:
        st.header("📖 Histórico de Ocorrências")
        if st.session_state.is_admin:
            lista_historico = fetch_data("SELECT * FROM historico ORDER BY id DESC")
        else:
            lista_historico = fetch_data("SELECT * FROM historico WHERE empresa=? ORDER BY id DESC", (st.session_state.nome_empresa,))
        
        if lista_historico:
            st.dataframe(lista_historico, use_container_width=True)
        else:
            st.info("O histórico de ocorrências está vazio.")
    tab_idx += 1

    # --- MÓDULO: GESTÃO DE PARCEIROS (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🏢 Gestão de Empresas Parceiras")
            with st.form("nova_empresa"):
                e_nome = st.text_input("Nome da Empresa (Login)")
                e_cnpj = st.text_input("CNPJ (Senha)")
                e_end = st.text_input("Endereço")
                e_tel = st.text_input("Telefone")
                e_resp = st.text_input("Responsável")
                
                if st.form_submit_button("Cadastrar Nova Empresa"):
                    if e_nome and e_cnpj:
                        execute_query("INSERT INTO empresas (nome, cnpj, endereco, telefone, responsavel) VALUES (?,?,?,?,?)", (e_nome, e_cnpj, e_end, e_tel, e_resp))
                        st.success(f"Empresa {e_nome} adicionada com sucesso!")
                    else:
                        st.error("Nome e CNPJ são obrigatórios.")

            lista_empresas = fetch_data("SELECT id, nome, cnpj, telefone, responsavel FROM empresas")
            if lista_empresas:
                st.dataframe(lista_empresas, use_container_width=True)
