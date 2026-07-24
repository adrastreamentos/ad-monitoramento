import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import urllib.parse
import io

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

# --- CONFIGURAÇÕES DA PÁGINA E IDENTIDADE VISUAL ---
st.set_page_config(page_title="AD Rastreamento Veicular", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #fdfdfd; }
    h1, h2, h3 { color: #4a0e4e; }
    .stButton>button { background-color: #8b0000; color: white; font-weight: bold; border-radius: 6px; border: none; transition: 0.3s; }
    .stButton>button:hover { background-color: #4a0e4e; color: white; border: 1px solid #8b0000; }
    div[data-testid="stSidebar"] { background-color: #4a0e4e; }
    div[data-testid="stSidebar"] * { color: white; }
    
    /* Estilização das Abas (Roxo com detalhe Vermelho) */
    button[data-baseweb="tab"] { background-color: transparent; border-radius: 5px 5px 0 0; }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #4a0e4e !important;
        border-bottom: 4px solid #8b0000 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] * { color: white !important; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- BANCO DE DADOS ---
DB_PATH = "ad_monitoramento.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS empresas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, cnpj TEXT, endereco TEXT, telefone TEXT, responsavel TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, documento TEXT, endereco TEXT, telefone TEXT, tipo_veic TEXT, placa TEXT, modelo TEXT, cor TEXT, empresa TEXT, status TEXT DEFAULT 'Ativo', ultima_atualizacao TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, cliente TEXT, placa TEXT, tipo TEXT, status TEXT, detalhes TEXT, empresa TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS auditoria (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, acao TEXT, modulo TEXT, detalhes TEXT, usuario TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS financeiro (id INTEGER PRIMARY KEY AUTOINCREMENT, mes TEXT, empresa TEXT, faturado REAL, recebido REAL, status TEXT, detalhes TEXT)''')
    conn.commit()
    conn.close()

init_db()

def fetch_data(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(query, params)
    columns = [desc[0] for desc in c.description]
    data = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return data

def execute_query(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def registrar_auditoria(acao, modulo, detalhes):
    usuario = st.session_state.nome_empresa
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    execute_query("INSERT INTO auditoria (data_hora, acao, modulo, detalhes, usuario) VALUES (?,?,?,?,?)", 
                  (agora, acao, modulo, detalhes, usuario))

# --- GERADOR DE PDF ---
def gerar_pdf_historico(df, empresa_nome):
    if FPDF is None:
        return None
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Relatório de Ocorrências - AD Rastreamento", ln=True, align='C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=f"Empresa / Parceiro: {empresa_nome}", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(35, 10, 'Data/Hora', border=1)
    pdf.cell(25, 10, 'Placa', border=1)
    pdf.cell(35, 10, 'Tipo', border=1)
    pdf.cell(30, 10, 'Status', border=1)
    pdf.cell(65, 10, 'Detalhes', border=1)
    pdf.ln()
    
    pdf.set_font("Arial", '', 8)
    for _, row in df.iterrows():
        detalhe_curto = str(row['detalhes'])[:45] + "..." if len(str(row['detalhes'])) > 45 else str(row['detalhes'])
        pdf.cell(35, 10, str(row['data_hora'])[:16], border=1)
        pdf.cell(25, 10, str(row['placa']), border=1)
        pdf.cell(35, 10, str(row['tipo']), border=1)
        pdf.cell(30, 10, str(row['status']), border=1)
        pdf.cell(65, 10, detalhe_curto, border=1)
        pdf.ln()
    return bytes(pdf.output(dest='S').encode('latin-1'))

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
        st.markdown("<p style='text-align: center; color: #8b0000; font-weight: bold;'>Central de Operações de Segurança</p>", unsafe_allow_html=True)
        
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
                        registrar_auditoria("Acesso", "Login", f"{res[0]['nome']} acessou o sistema.")
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
        st.markdown("### 🛡️ Missão AD")
        st.markdown("**Foco total na segurança, agilidade e comprometimento.** Nossa missão é garantir proteção máxima e resposta rápida para a nossa frota e a de nossos parceiros.")

    # Definição das Abas
    abas = ["👤 Clientes e Frotas", "📖 Histórico em PDF"]
    if st.session_state.is_admin:
        abas = ["🚨 Operação 24h", "👤 Clientes e Frotas", "📖 Histórico em PDF", "🏢 Parceiros", "💰 Financeiro", "🕵️ Auditoria"]
        
    tabs = st.tabs(abas)
    tab_idx = 0

    # --- ABA: OPERAÇÃO 24H (SÓ ADMIN) ---
    if st.session_state.is_admin:
        with tabs[tab_idx]:
            st.header("🚨 Central de Operações e Ocorrências 24h")
            busca_op = st.text_input("🔍 Buscar veículo (Placa, CPF ou Nome)")
            
            if busca_op and len(busca_op) >= 3:
                resultados = fetch_data(f"SELECT * FROM clientes WHERE status='Ativo' AND (lower(nome) LIKE '%{busca_op.lower()}%' OR lower(placa) LIKE '%{busca_op.lower()}%')")
                if resultados:
                    st.dataframe(resultados, use_container_width=True)
                    placas_disponiveis = [r['placa'] for r in resultados]
                    placa_sel = st.selectbox("Selecione a Placa para Atendimento:", placas_disponiveis)
                    
                    if placa_sel:
                        info_veic = next(item for item in resultados if item["placa"] == placa_sel)
                        col_f, col_m = st.columns(2)
                        
                        # Furto / Roubo
                        with col_f:
                            with st.form("form_furto"):
                                st.markdown("<h3 style='color: #8b0000;'>Abertura de Furto/Roubo</h3>", unsafe_allow_html=True)
                                tipo_oc = st.selectbox("Natureza", ["Furto", "Roubo"])
                                local_oc = st.text_input("Localização")
                                desc_oc = st.text_area("Descrição")
                                status_oc = st.selectbox("Status", ["INICIADO", "EM ANDAMENTO", "FINALIZADO"])
                                if st.form_submit_button("Salvar Ocorrência"):
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, tipo_oc, status_oc, f"Local: {local_oc} | {desc_oc}", info_veic['empresa']))
                                    registrar_auditoria("Registro", "Operação", f"Ocorrência de {tipo_oc} para {placa_sel}")
                                    st.success(f"Ocorrência salva!")
                        
                        # Monitoramento
                        with col_m:
                            with st.form("form_monitoramento"):
                                st.markdown("<h3 style='color: #4a0e4e;'>Monitoramento Técnico</h3>", unsafe_allow_html=True)
                                evento_mon = st.selectbox("Evento", ["Cerca Virtual", "Desconexão de Bateria", "Falta de Comunicação", "Outros"])
                                acao_mon = st.text_area("Ação da Central")
                                if st.form_submit_button("Salvar Monitoramento"):
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, "Monitoramento", "FINALIZADO", f"Evento: {evento_mon} | Ação: {acao_mon}", info_veic['empresa']))
                                    registrar_auditoria("Registro", "Monitoramento", f"Evento de {evento_mon} para {placa_sel}")
                                    st.success("Evento salvo!")
                else:
                    st.warning("Veículo não encontrado.")
        tab_idx += 1

    # --- ABA: CLIENTES E FROTAS (CRUD COMPLETO) ---
    with tabs[tab_idx]:
        st.header("👤 Gestão de Clientes e Frotas")
        t_cad_cli, t_edit_cli = st.tabs(["➕ Novo Cliente", "✏️ Editar / Excluir Cliente"])
        
        # Obter empresas disponíveis para garantir o fluxo de cadastro
        empresas_disp = fetch_data("SELECT nome FROM empresas")
        opcoes_emp = [e['nome'] for e in empresas_disp] if st.session_state.is_admin else [st.session_state.nome_empresa]
        
        with t_cad_cli:
            if not opcoes_emp:
                st.error("Nenhuma empresa parceira cadastrada! Cadastre a empresa primeiro na aba de Parceiros.")
            else:
                with st.form("novo_cliente"):
                    c1, c2 = st.columns(2)
                    nome = c1.text_input("Nome do Cliente *")
                    doc = c2.text_input("CPF/CNPJ")
                    end = c1.text_input("Endereço")
                    tel = c2.text_input("Telefone")
                    emp = c1.selectbox("Empresa Proprietária (Obrigatório)", opcoes_emp)
                    tipo = c2.selectbox("Tipo de Veículo", ["Carro", "Moto", "Caminhão", "Outro"])
                    placa = c1.text_input("Placa *")
                    mod = c2.text_input("Modelo")
                    cor = c1.text_input("Cor")
                    if st.form_submit_button("Salvar Cliente"):
                        if nome and placa:
                            agora = datetime.now().strftime('%d/%m/%Y %H:%M')
                            execute_query("INSERT INTO clientes (nome, documento, endereco, telefone, tipo_veic, placa, modelo, cor, empresa, status, ultima_atualizacao) VALUES (?,?,?,?,?,?,?,?,?,'Ativo',?)", 
                                      (nome, doc, end, tel, tipo, placa, mod, cor, emp, agora))
                            registrar_auditoria("Cadastro", "Clientes", f"Cliente {nome} ({placa}) adicionado por {emp}.")
                            st.success("Cadastrado com sucesso!")
                        else:
                            st.error("Nome e Placa são obrigatórios.")
        
        with t_edit_cli:
            if st.session_state.is_admin:
                lista_c = fetch_data("SELECT id, nome, placa, empresa FROM clientes")
            else:
                lista_c = fetch_data("SELECT id, nome, placa, empresa FROM clientes WHERE empresa=?", (st.session_state.nome_empresa,))
            
            if lista_c:
                cli_op = st.selectbox("Selecione o Cliente para Gerenciar", [f"{c['id']} - {c['nome']} ({c['placa']})" for c in lista_c])
                if cli_op:
                    id_sel = int(cli_op.split(" - ")[0])
                    cli_dados = fetch_data("SELECT * FROM clientes WHERE id=?", (id_sel,))[0]
                    
                    with st.form("edit_cliente"):
                        st.write("**Atualizar Dados:**")
                        n_nome = st.text_input("Nome", value=cli_dados['nome'])
                        n_placa = st.text_input("Placa", value=cli_dados['placa'])
                        n_status = st.selectbox("Status", ["Ativo", "Inativo"], index=0 if cli_dados['status']=='Ativo' else 1)
                        
                        col_btn1, col_btn2 = st.columns(2)
                        if col_btn1.form_submit_button("💾 Salvar Alterações"):
                            execute_query("UPDATE clientes SET nome=?, placa=?, status=? WHERE id=?", (n_nome, n_placa, n_status, id_sel))
                            registrar_auditoria("Edição", "Clientes", f"Cliente ID {id_sel} alterado.")
                            st.success("Atualizado!")
                            st.rerun()
                        if col_btn2.form_submit_button("🗑️ Excluir Cliente (Irreversível)"):
                            execute_query("DELETE FROM clientes WHERE id=?", (id_sel,))
                            registrar_auditoria("Exclusão", "Clientes", f"Cliente ID {id_sel} excluído.")
                            st.warning("Cliente excluído com sucesso!")
                            st.rerun()

        st.subheader("Base Atual de Clientes")
        if st.session_state.is_admin:
            df_clientes = pd.read_sql_query("SELECT id, nome, documento, placa, modelo, empresa, status FROM clientes", sqlite3.connect(DB_PATH))
        else:
            df_clientes = pd.read_sql_query(f"SELECT id, nome, documento, placa, modelo, status FROM clientes WHERE empresa='{st.session_state.nome_empresa}'", sqlite3.connect(DB_PATH))
        st.dataframe(df_clientes, use_container_width=True)
        
        if not st.session_state.is_admin:
            st.markdown("### 🚑 Apoio da Central")
            texto_wpp = f"🚨 *ATENDIMENTO INDIRETO* 🚨\n🏢 Parceiro acionando: {st.session_state.nome_empresa}\n⚠️ Precisamos de apoio na ocorrência!"
            url_wpp = f"https://wa.me/5584999305771?text={urllib.parse.quote(texto_wpp)}"
            st.markdown(f'<a href="{url_wpp}" target="_blank"><button style="background-color:#25D366; color:white; padding:10px; border-radius:5px; border:none; font-weight:bold;">🚨 Acionar Central via WhatsApp</button></a>', unsafe_allow_html=True)
    tab_idx += 1

    # --- ABA: HISTÓRICO & PDF ---
    with tabs[tab_idx]:
        st.header("📖 Histórico Operacional (Monitoramento e Ocorrências)")
        conn = sqlite3.connect(DB_PATH)
        if st.session_state.is_admin:
            df_hist = pd.read_sql_query("SELECT * FROM historico ORDER BY id DESC", conn)
        else:
            df_hist = pd.read_sql_query(f"SELECT * FROM historico WHERE empresa='{st.session_state.nome_empresa}' ORDER BY id DESC", conn)
        conn.close()
        
        st.dataframe(df_hist, use_container_width=True)
        
        if not df_hist.empty:
            if FPDF is not None:
                pdf_bytes = gerar_pdf_historico(df_hist, st.session_state.nome_empresa)
                if pdf_bytes:
                    st.download_button(label="📄 Baixar Relatório em PDF", data=pdf_bytes, file_name=f"Relatorio_{st.session_state.nome_empresa}.pdf", mime="application/pdf")
            else:
                st.warning("⚠️ Biblioteca 'fpdf' não instalada no servidor. Faça o download em CSV abaixo.")
                st.download_button(label="📄 Baixar Relatório (CSV)", data=df_hist.to_csv(index=False).encode('utf-8'), file_name="Relatorio.csv", mime="text/csv")
    tab_idx += 1

    # --- ABA: PARCEIROS (CRUD) (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🏢 Gestão de Empresas Parceiras")
            t_cad_emp, t_edit_emp = st.tabs(["➕ Cadastrar Parceiro", "✏️ Editar / Excluir Parceiro"])
            
            with t_cad_emp:
                with st.form("nova_empresa"):
                    e_nome = st.text_input("Nome da Empresa (Será o Login)")
                    e_cnpj = st.text_input("CNPJ (Será a Senha)")
                    e_resp = st.text_input("Responsável")
                    if st.form_submit_button("Registrar Parceiro"):
                        if e_nome and e_cnpj:
                            execute_query("INSERT INTO empresas (nome, cnpj, responsavel) VALUES (?,?,?)", (e_nome, e_cnpj, e_resp))
                            registrar_auditoria("Cadastro", "Parceiros", f"Empresa {e_nome} criada.")
                            st.success(f"Empresa {e_nome} criada! Agora ela já pode receber clientes.")
            
            with t_edit_emp:
                lista_e = fetch_data("SELECT id, nome FROM empresas")
                if lista_e:
                    emp_op = st.selectbox("Selecione a Empresa", [f"{e['id']} - {e['nome']}" for e in lista_e])
                    if emp_op:
                        id_emp = int(emp_op.split(" - ")[0])
                        if st.button("🗑️ Excluir Empresa (Irreversível)"):
                            execute_query("DELETE FROM empresas WHERE id=?", (id_emp,))
                            registrar_auditoria("Exclusão", "Parceiros", f"Empresa ID {id_emp} excluída.")
                            st.warning("Excluída com sucesso!")
                            st.rerun()

            st.dataframe(pd.read_sql_query("SELECT id, nome, cnpj, responsavel FROM empresas", sqlite3.connect(DB_PATH)), use_container_width=True)
        tab_idx += 1

    # --- ABA: FINANCEIRO (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("💰 Controle Financeiro de Parceiros")
            mes_busca = st.text_input("🔍 Filtrar por Mês (Ex: 06/2026)")
            
            with st.expander("➕ Lançar Faturamento"):
                with st.form("form_fin"):
                    f_mes = st.text_input("Mês de Referência (Ex: 06/2026)")
                    f_emp = st.selectbox("Empresa", [e['nome'] for e in fetch_data("SELECT nome FROM empresas")])
                    f_fat = st.number_input("Valor Faturado (R$)", min_value=0.0, format="%.2f")
                    f_rec = st.number_input("Valor Recebido/Pago (R$)", min_value=0.0, format="%.2f")
                    f_stat = st.selectbox("Status", ["Pendente", "Pago Parcial", "Pago Integral"])
                    if st.form_submit_button("Salvar Lançamento"):
                        execute_query("INSERT INTO financeiro (mes, empresa, faturado, recebido, status) VALUES (?,?,?,?,?)", 
                                      (f_mes, f_emp, f_fat, f_rec, f_stat))
                        st.success("Lançamento salvo com sucesso!")
            
            q_fin = f"SELECT * FROM financeiro WHERE mes LIKE '%{mes_busca}%'" if mes_busca else "SELECT * FROM financeiro"
            df_fin = pd.read_sql_query(q_fin, sqlite3.connect(DB_PATH))
            st.dataframe(df_fin, use_container_width=True)
        tab_idx += 1

    # --- ABA: AUDITORIA (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🕵️ Auditoria e Rastreabilidade do Sistema")
            st.markdown("Acompanhe em tempo real tudo o que as empresas parceiras incluem, editam ou excluem no sistema.")
            df_auditoria = pd.read_sql_query("SELECT * FROM auditoria ORDER BY id DESC", sqlite3.connect(DB_PATH))
            st.dataframe(df_auditoria, use_container_width=True)
