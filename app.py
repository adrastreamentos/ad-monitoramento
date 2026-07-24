import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import urllib.parse
from supabase import create_client, Client

# --- CONFIGURAÇÕES E CORES (AD RASTREAMENTO VEICULAR) ---
st.set_page_config(page_title="AD Rastreamento Veicular", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    /* Identidade visual: Roxo e Vermelho Escuro */
    .stApp { background-color: #fdfdfd; }
    h1, h2, h3 { color: #4a0e4e; } /* Roxo */
    .stButton>button { background-color: #8b0000; color: white; font-weight: bold; border-radius: 6px; border: none; }
    .stButton>button:hover { background-color: #4a0e4e; color: white; }
    div[data-testid="stSidebar"] { background-color: #4a0e4e; }
    div[data-testid="stSidebar"] * { color: white; }
</style>
""", unsafe_allow_html=True)

# --- CHAVES DO SUPABASE (Mantidas conforme o original) ---
SUPABASE_URL = "https://gfhgehiygflvkxqbbygt.supabase.co"
SUPABASE_KEY = "sb_publishable_gw3fItEipuMZImIfNTJBjA_4nzrib9W"

@st.cache_resource
def get_supabase():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.sidebar.error("Aviso: Sem conexão com a nuvem no momento.")
        return None

supabase = get_supabase()

# --- BANCO DE DADOS LOCAL ---
DB_PATH = "banco_ad_v3.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS empresas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, cnpj TEXT, endereco TEXT, telefone TEXT, responsavel TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, documento TEXT, endereco TEXT, telefone TEXT, tipo_veic TEXT, placa TEXT, modelo TEXT, cor TEXT, empresa TEXT, status TEXT DEFAULT 'Ativo', ultima_atualizacao TEXT DEFAULT '')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS historico (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, cliente TEXT, placa TEXT, tipo TEXT, status TEXT, detalhes TEXT, empresa TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- CONTROLE DE SESSÃO (LOGIN) ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.is_admin = False
    st.session_state.nome_empresa = ""

# ==========================================
# TELA DE LOGIN
# ==========================================
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>🛡️ AD Rastreamento Veicular</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #8b0000; font-weight: bold;'>Central de Operações e Apoio</p>", unsafe_allow_html=True)
        
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
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("SELECT nome FROM empresas WHERE nome=? AND cnpj=?", (user, senha))
                    res = cursor.fetchone()
                    conn.close()
                    
                    if res:
                        st.session_state.logged_in = True
                        st.session_state.is_admin = False
                        st.session_state.nome_empresa = res[0]
                        st.rerun()
                    else:
                        st.error("Acesso Negado: Login ou Senha incorretos.")

# ==========================================
# SISTEMA PRINCIPAL (PÓS-LOGIN)
# ==========================================
else:
    # BARRA LATERAL
    with st.sidebar:
        st.write(f"👤 **Conectado como:** {st.session_state.nome_empresa}")
        if st.button("🚪 Sair do Sistema"):
            st.session_state.logged_in = False
            st.rerun()
        st.markdown("---")
        st.markdown("Garantindo segurança, agilidade e proteção contínua para nossas motoristas.")

    # ABAS
    abas = ["👤 Clientes e Frotas", "📖 Histórico de Ocorrências"]
    if st.session_state.is_admin:
        abas.insert(0, "🚨 Operação 24h")
        abas.append("🏢 Gestão de Parceiros")
        
    tabs = st.tabs(abas)
    
    tab_idx = 0

    # ==========================
    # 1. ABA OPERAÇÃO 24H (SÓ ADMIN)
    # ==========================
    if st.session_state.is_admin:
        with tabs[tab_idx]:
            st.header("🚨 Central de Operações e Ocorrências 24h")
            
            busca_op = st.text_input("🔍 Buscar veículo por Placa, CPF ou Nome (Apenas Ativos)")
            if busca_op and len(busca_op) >= 3:
                conn = sqlite3.connect(DB_PATH)
                df_busca = pd.read_sql_query(f"SELECT nome, documento, placa, modelo, empresa FROM clientes WHERE status='Ativo' AND (lower(nome) LIKE '%{busca_op.lower()}%' OR lower(placa) LIKE '%{busca_op.lower()}%')", conn)
                conn.close()
                
                if not df_busca.empty:
                    st.dataframe(df_busca, use_container_width=True)
                    
                    st.subheader("Registrar Atendimento para Veículo Encontrado")
                    placa_sel = st.selectbox("Selecione a Placa para o atendimento:", df_busca['placa'].unique())
                    
                    if placa_sel:
                        info_veic = df_busca[df_busca['placa'] == placa_sel].iloc[0]
                        
                        col_f, col_m = st.columns(2)
                        with col_f:
                            with st.form("form_furto"):
                                st.markdown(f"<h3 style='color: #8b0000;'>Abertura de Furto/Roubo</h3>", unsafe_allow_html=True)
                                tipo_ocorrencia = st.selectbox("Natureza", ["Furto", "Roubo"])
                                local_oc = st.text_input("Localização")
                                desc_oc = st.text_area("Descrição do Ocorrido")
                                status_oc = st.selectbox("Status", ["INICIADO", "EM ANDAMENTO", "FINALIZADO"])
                                if st.form_submit_button("Salvar no Histórico"):
                                    conn = sqlite3.connect(DB_PATH)
                                    c = conn.cursor()
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    c.execute("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, tipo_ocorrencia, status_oc, f"Local: {local_oc} | Desc: {desc_oc}", info_veic['empresa']))
                                    conn.commit()
                                    conn.close()
                                    if supabase:
                                        try:
                                            supabase.table("historico").insert({"data_hora": agora, "cliente": info_veic['nome'], "placa": placa_sel, "tipo": tipo_ocorrencia, "status": status_oc, "detalhes": f"Local: {local_oc} | Desc: {desc_oc}", "empresa": info_veic['empresa']}).execute()
                                        except: pass
                                    st.success(f"Ocorrência de {tipo_ocorrencia} salva com sucesso!")

                        with col_m:
                            with st.form("form_monitoramento"):
                                st.markdown(f"<h3 style='color: #4a0e4e;'>Registro de Monitoramento</h3>", unsafe_allow_html=True)
                                evento_mon = st.selectbox("Evento", ["Cerca Virtual", "Desconexão de Bateria", "Falta de Comunicação", "Outros"])
                                acao_mon = st.text_area("Ação Realizada")
                                if st.form_submit_button("Salvar Monitoramento"):
                                    conn = sqlite3.connect(DB_PATH)
                                    c = conn.cursor()
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    c.execute("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, "Monitoramento", "FINALIZADO", f"Evento: {evento_mon} | Ação: {acao_mon}", info_veic['empresa']))
                                    conn.commit()
                                    conn.close()
                                    st.success("Evento de monitoramento registrado!")
                else:
                    st.warning("Nenhum veículo ativo encontrado com esse termo.")
                    
        tab_idx += 1

    # ==========================
    # 2. ABA CLIENTES E FROTAS
    # ==========================
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
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        agora = datetime.now().strftime('%d/%m/%Y %H:%M')
                        c.execute("INSERT INTO clientes (nome, documento, endereco, telefone, tipo_veic, placa, modelo, cor, empresa, status, ultima_atualizacao) VALUES (?,?,?,?,?,?,?,?,?,'Ativo',?)", 
                                  (nome, doc, end, tel, tipo, placa, mod, cor, emp, agora))
                        conn.commit()
                        conn.close()
                        if supabase:
                            try:
                                supabase.table("clientes").insert({"nome": nome, "documento": doc, "endereco": end, "telefone": tel, "tipo_veic": tipo, "placa": placa, "modelo": mod, "cor": cor, "empresa": emp, "status": "Ativo"}).execute()
                            except: pass
                        st.success("Cliente cadastrado com sucesso!")
                    else:
                        st.error("Nome e Placa são obrigatórios.")

        st.subheader("Base de Clientes")
        conn = sqlite3.connect(DB_PATH)
        if st.session_state.is_admin:
            df_clientes = pd.read_sql_query("SELECT id, nome, documento, telefone, placa, modelo, empresa, status FROM clientes", conn)
        else:
            df_clientes = pd.read_sql_query(f"SELECT id, nome, documento, telefone, placa, modelo, status FROM clientes WHERE empresa='{st.session_state.nome_empresa}'", conn)
        conn.close()
        
        st.dataframe(df_clientes, use_container_width=True)
        
        if not st.session_state.is_admin:
            st.markdown("### 🚑 Apoio da Central")
            texto_wpp = f"🚨 *ATENDIMENTO INDIRETO* 🚨\n\n🏢 Parceiro acionando: {st.session_state.nome_empresa}\n⚠️ O cliente entrou em contato direto. Precisamos de apoio na ocorrência!"
            url_wpp = f"https://wa.me/5584999305771?text={urllib.parse.quote(texto_wpp)}"
            st.markdown(f'<a href="{url_wpp}" target="_blank"><button style="background-color:#25D366; color:white; padding:10px; border-radius:5px; border:none; font-weight:bold;">🚨 Acionar Central AD via WhatsApp</button></a>', unsafe_allow_html=True)
            
    tab_idx += 1

    # ==========================
    # 3. ABA HISTÓRICO
    # ==========================
    with tabs[tab_idx]:
        st.header("📖 Histórico de Ocorrências")
        
        conn = sqlite3.connect(DB_PATH)
        if st.session_state.is_admin:
            df_hist = pd.read_sql_query("SELECT * FROM historico ORDER BY id DESC", conn)
        else:
            df_hist = pd.read_sql_query(f"SELECT * FROM historico WHERE empresa='{st.session_state.nome_empresa}' ORDER BY id DESC", conn)
        conn.close()
        
        st.dataframe(df_hist, use_container_width=True)
        
        # Simulação simples de exportação de relatório PDF convertendo para CSV via botão nativo do Streamlit
        st.download_button(
            label="📄 Fazer Download do Relatório (CSV)",
            data=df_hist.to_csv(index=False).encode('utf-8'),
            file_name=f"Relatorio_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        
    tab_idx += 1

    # ==========================
    # 4. ABA GESTÃO DE PARCEIROS (SÓ ADMIN)
    # ==========================
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🏢 Gestão de Empresas Parceiras")
            
            with st.form("nova_empresa"):
                e_nome = st.text_input("Nome da Empresa (Login)")
                e_cnpj = st.text_input("CNPJ (Senha)")
                e_end = st.text_input("Endereço")
                e_tel = st.text_input("Telefone")
                e_resp = st.text_input("Responsável")
                
                if st.form_submit_button("Salvar Empresa Parceira"):
                    if e_nome and e_cnpj:
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        c.execute("INSERT INTO empresas (nome, cnpj, endereco, telefone, responsavel) VALUES (?,?,?,?,?)", (e_nome, e_cnpj, e_end, e_tel, e_resp))
                        conn.commit()
                        conn.close()
                        st.success(f"Empresa {e_nome} adicionada!")
                    else:
                        st.error("Nome e CNPJ são obrigatórios.")

            conn = sqlite3.connect(DB_PATH)
            df_empresas = pd.read_sql_query("SELECT id, nome, cnpj, telefone, responsavel FROM empresas", conn)
            conn.close()
            st.dataframe(df_empresas, use_container_width=True)
