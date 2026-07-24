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
    
    /* Ajuste para pastas (expanders) */
    div[data-testid="stExpander"] { border-left: 4px solid #4a0e4e; }
    
    /* Ajuste botões de rádio (Ações) */
    div[role="radiogroup"] { flex-wrap: wrap; gap: 15px; }
    
    /* Estilo Ficha de Atendimento */
    .ficha-box { border: 2px solid #4a0e4e; padding: 20px; border-radius: 10px; background-color: #fafafa; margin-top: 15px;}
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

# --- GERADOR DE PDF ESPECÍFICO ---
def gerar_pdf_individual(dados_relatorio, empresa_nome):
    if FPDF is None:
        return None
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Relatório de Atendimento Oficial", ln=True, align='C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=f"Emitido por: {empresa_nome}", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(50, 10, "Detalhes da Ocorrência:", ln=True)
    pdf.set_font("Arial", '', 10)
    
    pdf.cell(40, 10, "Data/Hora:", border=1)
    pdf.cell(150, 10, str(dados_relatorio['data_hora']), border=1, ln=True)
    
    pdf.cell(40, 10, "Cliente:", border=1)
    pdf.cell(150, 10, str(dados_relatorio['cliente']), border=1, ln=True)
    
    pdf.cell(40, 10, "Placa:", border=1)
    pdf.cell(150, 10, str(dados_relatorio['placa']), border=1, ln=True)
    
    pdf.cell(40, 10, "Tipo de Serviço:", border=1)
    pdf.cell(150, 10, str(dados_relatorio['tipo']), border=1, ln=True)
    
    pdf.cell(40, 10, "Status Atual:", border=1)
    pdf.cell(150, 10, str(dados_relatorio['status']), border=1, ln=True)
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(50, 10, "Descrição / Ações Tomadas:", ln=True)
    pdf.set_font("Arial", '', 10)
    pdf.multi_cell(0, 8, txt=str(dados_relatorio['detalhes']))
    
    return bytes(pdf.output(dest='S').encode('latin-1'))

# --- CONTROLE DE SESSÃO ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.is_admin = False
    st.session_state.nome_empresa = ""
if 'acao_clientes' not in st.session_state:
    st.session_state.acao_clientes = "Listar"
if 'acao_parceiros' not in st.session_state:
    st.session_state.acao_parceiros = "Listar"

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
            st.session_state.is_admin = False
            st.session_state.nome_empresa = ""
            st.rerun()
        st.markdown("---")
        st.markdown("### 🛡️ Missão AD")
        st.markdown("**Foco total na segurança, agilidade e comprometimento.** Nossa missão é garantir proteção máxima e resposta rápida para a nossa frota e a de nossos parceiros.")

    abas = ["👤 Clientes", "📖 Relatórios & PDF"]
    if st.session_state.is_admin:
        abas = ["🚨 Central 24h", "👤 Clientes", "📖 Relatórios & PDF", "🏢 Empresas", "💰 Financeiro", "🕵️ Auditoria"]
        
    tabs = st.tabs(abas)
    tab_idx = 0

    # --- ABA: OPERAÇÃO 24H (SÓ ADMIN) ---
    if st.session_state.is_admin:
        with tabs[tab_idx]:
            st.header("🚨 Central de Operações e Ocorrências 24h")
            busca_op = st.text_input("🔍 Buscar veículo (Digite Nome, Placa ou CPF)")
            
            if busca_op and len(busca_op) >= 3:
                q_busca = f"SELECT * FROM clientes WHERE status='Ativo' AND (lower(nome) LIKE '%{busca_op.lower()}%' OR lower(placa) LIKE '%{busca_op.lower()}%' OR lower(documento) LIKE '%{busca_op.lower()}%')"
                resultados = fetch_data(q_busca)
                
                if resultados:
                    st.success("Veículos encontrados! Selecione abaixo.")
                    placas_disponiveis = [f"{r['placa']} - {r['nome']}" for r in resultados]
                    placa_sel_texto = st.selectbox("Selecione o Veículo para Atendimento:", placas_disponiveis)
                    
                    if placa_sel_texto:
                        placa_sel = placa_sel_texto.split(" - ")[0]
                        info_veic = next(item for item in resultados if item["placa"] == placa_sel)
                        
                        st.markdown("---")
                        tipo_servico = st.radio("📋 **Ação na Central:**", ["Abertura de Furto/Roubo", "Finalizar Ocorrência Ativa", "Monitoramento Técnico"], horizontal=True)
                        
                        if tipo_servico == "Abertura de Furto/Roubo":
                            with st.form("form_furto", clear_on_submit=True):
                                st.markdown("<h3 style='color: #8b0000;'>Abertura de Furto/Roubo (Início)</h3>", unsafe_allow_html=True)
                                tipo_oc = st.selectbox("Natureza", ["Furto", "Roubo"])
                                local_oc = st.text_input("Localização do Fato")
                                desc_oc = st.text_area("Descrição / Dinâmica")
                                st.info("ℹ️ Status automático: EM ANDAMENTO.")
                                
                                if st.form_submit_button("Salvar Ocorrência"):
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, tipo_oc, "EM ANDAMENTO", f"Local: {local_oc} | {desc_oc}", info_veic['empresa']))
                                    registrar_auditoria("Registro", "Operação", f"Ocorrência de {tipo_oc} INICIADA para {placa_sel}")
                                    st.success(f"Salvo! Limpando tela...")
                                    st.rerun()
                        
                        elif tipo_servico == "Finalizar Ocorrência Ativa":
                            pendentes = fetch_data("SELECT * FROM historico WHERE placa=? AND status='EM ANDAMENTO'", (placa_sel,))
                            if pendentes:
                                with st.form("form_finalizar", clear_on_submit=True):
                                    id_pendente = pendentes[0]['id']
                                    st.write(f"**Pendente:** {pendentes[0]['tipo']} em {pendentes[0]['data_hora']}")
                                    conclusao_oc = st.text_area("Desfecho (Recuperado, etc.)")
                                    if st.form_submit_button("Finalizar Ocorrência"):
                                        novo_detalhe = pendentes[0]['detalhes'] + f" | DESFECHO: {conclusao_oc}"
                                        execute_query("UPDATE historico SET status='FINALIZADO', detalhes=? WHERE id=?", (novo_detalhe, id_pendente))
                                        registrar_auditoria("Atualização", "Operação", f"Ocorrência ID {id_pendente} FINALIZADA.")
                                        st.success("Finalizada! Limpando tela...")
                                        st.rerun()
                            else:
                                st.warning("Não há ocorrências em andamento para este veículo.")
                        
                        elif tipo_servico == "Monitoramento Técnico":
                            with st.form("form_monitoramento", clear_on_submit=True):
                                st.markdown("<h3 style='color: #4a0e4e;'>Monitoramento Técnico</h3>", unsafe_allow_html=True)
                                evento_mon = st.selectbox("Evento", ["Cerca Virtual", "Desconexão de Bateria", "Falta de Comunicação", "Outros"])
                                acao_mon = st.text_area("Ação da Central")
                                if st.form_submit_button("Salvar Monitoramento"):
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, "Monitoramento", "FINALIZADO", f"Evento: {evento_mon} | Ação: {acao_mon}", info_veic['empresa']))
                                    registrar_auditoria("Registro", "Monitoramento", f"Evento para {placa_sel}")
                                    st.success("Salvo! Limpando tela...")
                                    st.rerun()
                else:
                    st.warning("Nenhum veículo encontrado com este termo.")
        tab_idx += 1

    # --- ABA: CLIENTES E FROTAS ---
    with tabs[tab_idx]:
        st.header("👤 Gerenciamento de Clientes (Frota Ilimitada e Endereço)")
        
        acao_clientes = st.radio("Ação Clientes:", ["Listar", "Incluir Novo", "Importação em Lote", "Editar", "Excluir"], horizontal=True, key="acao_clientes")
        st.markdown("---")
        
        empresas_disp = fetch_data("SELECT nome FROM empresas")
        opcoes_emp = [e['nome'] for e in empresas_disp] if st.session_state.is_admin else [st.session_state.nome_empresa]
        q_clientes = "SELECT * FROM clientes" if st.session_state.is_admin else f"SELECT * FROM clientes WHERE empresa='{st.session_state.nome_empresa}'"
        df_clientes = pd.read_sql_query(q_clientes, sqlite3.connect(DB_PATH))

        if acao_clientes == "Listar":
            if not df_clientes.empty:
                df_export = df_clientes[['nome', 'documento', 'endereco', 'telefone', 'tipo_veic', 'placa', 'modelo', 'cor']]
                df_export.columns = ['Nome', 'CPF/CNPJ', 'Endereço', 'Telefone', 'Tipo de Veículo', 'Placa', 'Modelo', 'Cor']
                st.download_button(label="📥 Baixar Base de Clientes (CSV Inteligente)", data=df_export.to_csv(index=False).encode('utf-8'), file_name="Base_Clientes_AD.csv", mime="text/csv")
                
                empresas_ativas = df_clientes['empresa'].unique()
                for emp_ativa in empresas_ativas:
                    with st.expander(f"📁 Clientes da Empresa: {emp_ativa}"):
                        df_emp = df_clientes[df_clientes['empresa'] == emp_ativa]
                        st.dataframe(df_emp[['nome', 'documento', 'placa', 'modelo', 'status']], use_container_width=True)
            else:
                st.info("Nenhum cliente cadastrado no momento.")
                
        elif acao_clientes == "Incluir Novo":
            if not opcoes_emp:
                st.error("Nenhuma empresa parceira cadastrada! Cadastre a empresa primeiro.")
            else:
                st.subheader("➕ Incluir Novo Cliente")
                with st.form("novo_cliente", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    nome = c1.text_input("Nome do Cliente *")
                    doc = c2.text_input("CPF/CNPJ")
                    end = c1.text_input("Endereço")
                    tel = c2.text_input("Telefone")
                    emp = c1.selectbox("Empresa (Pasta) *", opcoes_emp)
                    tipo = c2.selectbox("Tipo de Veículo", ["Carro", "Moto", "Caminhão", "Outro"])
                    placa = c1.text_input("Placa *")
                    mod = c2.text_input("Modelo")
                    cor = c1.text_input("Cor")
                    if st.form_submit_button("Salvar Cliente"):
                        if nome and placa:
                            agora = datetime.now().strftime('%d/%m/%Y %H:%M')
                            execute_query("INSERT INTO clientes (nome, documento, endereco, telefone, tipo_veic, placa, modelo, cor, empresa, status, ultima_atualizacao) VALUES (?,?,?,?,?,?,?,?,?,'Ativo',?)", 
                                      (nome, doc, end, tel, tipo, placa, mod, cor, emp, agora))
                            registrar_auditoria("Cadastro", "Clientes", f"Cliente {nome} adicionado na pasta {emp}.")
                            st.session_state.acao_clientes = "Listar"
                            st.rerun()
                        else:
                            st.error("Nome e Placa são obrigatórios.")
                            
        elif acao_clientes == "Importação em Lote":
            st.info("📥 Funcionalidade de Importação em Lote (CSV) estará disponível na próxima atualização estrutural.")
            
        elif acao_clientes in ["Editar", "Excluir"]:
            busca = st.text_input("🔍 Buscar Cliente na Lista (Nome, Placa ou CPF):")
            if busca and len(busca) >= 3:
                q_busca_cli = f"SELECT * FROM clientes WHERE lower(nome) LIKE '%{busca.lower()}%' OR lower(placa) LIKE '%{busca.lower()}%' OR lower(documento) LIKE '%{busca.lower()}%'"
                if not st.session_state.is_admin:
                    q_busca_cli += f" AND empresa='{st.session_state.nome_empresa}'"
                
                res_cli = fetch_data(q_busca_cli)
                if res_cli:
                    lista_opcoes = [f"{c['id']} - {c['nome']} ({c['placa']})" for c in res_cli]
                    cli_selecionado = st.selectbox("Selecione o Cliente:", [""] + lista_opcoes)
                    
                    if cli_selecionado:
                        id_sel = int(cli_selecionado.split(" - ")[0])
                        dados_c = next(item for item in res_cli if item["id"] == id_sel)
                        
                        if acao_clientes == "Editar":
                            with st.form(f"form_edit_cli", clear_on_submit=True):
                                st.write("**Atualizando Dados:**")
                                en_nome = st.text_input("Nome", value=dados_c['nome'])
                                en_placa = st.text_input("Placa", value=dados_c['placa'])
                                en_status = st.selectbox("Status", ["Ativo", "Inativo"], index=0 if dados_c['status']=='Ativo' else 1)
                                if st.form_submit_button("💾 Salvar Alterações"):
                                    execute_query("UPDATE clientes SET nome=?, placa=?, status=? WHERE id=?", (en_nome, en_placa, en_status, id_sel))
                                    registrar_auditoria("Edição", "Clientes", f"Cliente ID {id_sel} alterado.")
                                    st.session_state.acao_clientes = "Listar"
                                    st.rerun()
                        
                        elif acao_clientes == "Excluir":
                            st.warning(f"Tem certeza que deseja excluir o cliente **{dados_c['nome']}**?")
                            if st.button("🗑️ Excluir Cliente (Irreversível)"):
                                execute_query("DELETE FROM clientes WHERE id=?", (id_sel,))
                                registrar_auditoria("Exclusão", "Clientes", f"Cliente ID {id_sel} excluído.")
                                st.session_state.acao_clientes = "Listar"
                                st.rerun()
                else:
                    st.warning("Nenhum cliente encontrado com esse termo.")
    tab_idx += 1

    # --- ABA: HISTÓRICO & PDF ---
    with tabs[tab_idx]:
        st.header("📖 Relatórios & PDF")
        
        col_f1, col_f2 = st.columns(2)
        filtro_busca_hist = col_f1.text_input("🔍 Filtrar por Placa, Nome ou CPF")
        filtro_periodo = col_f2.text_input("📅 Filtrar por Data (Ex: 24/07/2026)")
        
        conn = sqlite3.connect(DB_PATH)
        if st.session_state.is_admin:
            query_h = "SELECT * FROM historico WHERE 1=1"
            params_h = []
        else:
            query_h = "SELECT * FROM historico WHERE empresa=?"
            params_h = [st.session_state.nome_empresa]
            
        if filtro_busca_hist:
            query_h += " AND (lower(cliente) LIKE ? OR lower(placa) LIKE ?)"
            params_h.extend([f"%{filtro_busca_hist.lower()}%", f"%{filtro_busca_hist.lower()}%"])
        if filtro_periodo:
            query_h += " AND data_hora LIKE ?"
            params_h.append(f"%{filtro_periodo}%")
            
        query_h += " ORDER BY id DESC"
        res_historico = fetch_data(query_h, params=params_h)
        df_hist = pd.DataFrame(res_historico)
        conn.close()
        
        # Tabela reduzida (Resumo)
        if not df_hist.empty:
            df_resumo = df_hist[['id', 'data_hora', 'cliente', 'placa', 'tipo', 'status']]
            st.dataframe(df_resumo, use_container_width=True)
            
            st.markdown("---")
            st.markdown("### 🔎 Visualizar Ficha de Atendimento")
            lista_hist = [f"{h['id']} - {h['placa']} ({h['data_hora']})" for h in res_historico]
            rel_selecionado = st.selectbox("Selecione um registro da lista acima para ver detalhes ou baixar o PDF:", [""] + lista_hist)
            
            if rel_selecionado:
                id_rel = int(rel_selecionado.split(" - ")[0])
                dados_rel = next(item for item in res_historico if item["id"] == id_rel)
                
                # Exibir os detalhes visualmente na tela
                st.markdown(f"""
                <div class="ficha-box">
                    <h4 style="color:#8b0000; text-align:center;">Ficha de Ocorrência nº {dados_rel['id']}</h4>
                    <hr>
                    <p><b>Data/Hora:</b> {dados_rel['data_hora']}</p>
                    <p><b>Cliente:</b> {dados_rel['cliente']}</p>
                    <p><b>Placa:</b> {dados_rel['placa']}</p>
                    <p><b>Tipo de Serviço:</b> {dados_rel['tipo']}</p>
                    <p><b>Status:</b> {dados_rel['status']}</p>
                    <hr>
                    <p><b>Detalhes / Ações Tomadas:</b></p>
                    <p>{dados_rel['detalhes']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Opção de baixar o PDF desta ficha específica
                if FPDF is not None:
                    pdf_bytes = gerar_pdf_individual(dados_rel, st.session_state.nome_empresa)
                    if pdf_bytes:
                        st.download_button(label="📄 Baixar esta Ficha em PDF", data=pdf_bytes, file_name=f"Ocorrencia_{dados_rel['placa']}.pdf", mime="application/pdf")
                else:
                    st.error("⚠️ Biblioteca 'fpdf' ausente no servidor. Configure o requirements.txt.")
        else:
            st.info("Nenhum histórico encontrado.")
        
        if st.session_state.is_admin and not df_hist.empty:
            st.markdown("---")
            with st.expander("⚙️ Excluir Registro do Histórico (Admin)"):
                id_del_hist = st.selectbox("ID do Histórico para remover:", [""] + list(df_hist['id'].astype(str)))
                if id_del_hist and st.button("🗑️ Excluir Registro Selecionado"):
                    execute_query("DELETE FROM historico WHERE id=?", (int(id_del_hist),))
                    registrar_auditoria("Exclusão", "Histórico", f"Registro ID {id_del_hist} removido.")
                    st.rerun()
    tab_idx += 1

    # --- ABA: PARCEIROS (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🏢 Gerenciamento de Empresas Parceiras")
            
            acao_parceiros = st.radio("Ação Empresas:", ["Listar", "Incluir Nova", "Editar", "Excluir"], horizontal=True, key="acao_parceiros")
            st.markdown("---")
            
            df_empresas = pd.read_sql_query("SELECT * FROM empresas", sqlite3.connect(DB_PATH))
            
            if acao_parceiros == "Listar":
                if not df_empresas.empty:
                    for _, emp in df_empresas.iterrows():
                        with st.expander(f"📁 Empresa: {emp['nome']}"):
                            st.write(f"**CNPJ/Senha:** {emp['cnpj']} | **Responsável:** {emp['responsavel']}")
                            st.write(f"**Telefone:** {emp['telefone']} | **Endereço:** {emp['endereco']}")
                else:
                    st.info("Nenhuma empresa parceira cadastrada.")
            
            elif acao_parceiros == "Incluir Nova":
                with st.form("nova_empresa", clear_on_submit=True):
                    e_nome = st.text_input("Nome da Empresa (Será o Login) *")
                    e_cnpj = st.text_input("CNPJ (Será a Senha) *")
                    e_end = st.text_input("Endereço")
                    e_tel = st.text_input("Telefone")
                    e_resp = st.text_input("Responsável")
                    if st.form_submit_button("Registrar Parceiro"):
                        if e_nome and e_cnpj:
                            execute_query("INSERT INTO empresas (nome, cnpj, endereco, telefone, responsavel) VALUES (?,?,?,?,?)", (e_nome, e_cnpj, e_end, e_tel, e_resp))
                            registrar_auditoria("Cadastro", "Parceiros", f"Empresa {e_nome} criada.")
                            st.session_state.acao_parceiros = "Listar"
                            st.rerun()
                        else:
                            st.error("Nome e CNPJ são obrigatórios.")
                            
            elif acao_parceiros in ["Editar", "Excluir"]:
                busca_emp = st.text_input("🔍 Buscar Empresa na Lista (Nome ou CNPJ):")
                if busca_emp and len(busca_emp) >= 3:
                    res_emp = fetch_data(f"SELECT * FROM empresas WHERE lower(nome) LIKE '%{busca_emp.lower()}%' OR cnpj LIKE '%{busca_emp}%'")
                    if res_emp:
                        lista_opcoes_e = [f"{e['id']} - {e['nome']}" for e in res_emp]
                        emp_selecionada = st.selectbox("Selecione a Empresa:", [""] + lista_opcoes_e)
                        
                        if emp_selecionada:
                            id_emp = int(emp_selecionada.split(" - ")[0])
                            dados_e = next(item for item in res_emp if item["id"] == id_emp)
                            
                            if acao_parceiros == "Editar":
                                with st.form(f"form_edit_emp", clear_on_submit=True):
                                    ne_nome = st.text_input("Nome", value=dados_e['nome'])
                                    ne_resp = st.text_input("Responsável", value=dados_e['responsavel'])
                                    ne_tel = st.text_input("Telefone", value=dados_e['telefone'])
                                    ne_end = st.text_input("Endereço", value=dados_e['endereco'])
                                    if st.form_submit_button("💾 Salvar Alterações"):
                                        execute_query("UPDATE empresas SET nome=?, responsavel=?, telefone=?, endereco=? WHERE id=?", (ne_nome, ne_resp, ne_tel, ne_end, id_emp))
                                        registrar_auditoria("Edição", "Parceiros", f"Parceiro ID {id_emp} alterado.")
                                        st.session_state.acao_parceiros = "Listar"
                                        st.rerun()
                            
                            elif acao_parceiros == "Excluir":
                                st.warning(f"Tem certeza que deseja excluir a empresa **{dados_e['nome']}**?")
                                if st.button("🗑️ Excluir Parceiro"):
                                    execute_query("DELETE FROM empresas WHERE id=?", (id_emp,))
                                    registrar_auditoria("Exclusão", "Parceiros", f"Parceiro ID {id_emp} excluído.")
                                    st.session_state.acao_parceiros = "Listar"
                                    st.rerun()
                    else:
                        st.warning("Nenhuma empresa encontrada com esse termo.")
        tab_idx += 1

    # --- ABA: FINANCEIRO (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("💰 Controle Financeiro")
            mes_busca = st.text_input("🔍 Filtrar por Mês")
            with st.expander("➕ Lançar Faturamento"):
                with st.form("form_fin", clear_on_submit=True):
                    f_mes = st.text_input("Mês (Ex: 07/2026)")
                    f_emp = st.selectbox("Empresa", [e['nome'] for e in fetch_data("SELECT nome FROM empresas")])
                    f_fat = st.number_input("Valor Faturado (R$)", min_value=0.0, format="%.2f")
                    f_rec = st.number_input("Valor Recebido/Pago (R$)", min_value=0.0, format="%.2f")
                    f_stat = st.selectbox("Status", ["Pendente", "Pago Parcial", "Pago Integral"])
                    if st.form_submit_button("Salvar Lançamento"):
                        execute_query("INSERT INTO financeiro (mes, empresa, faturado, recebido, status) VALUES (?,?,?,?,?)", 
                                      (f_mes, f_emp, f_fat, f_rec, f_stat))
                        st.rerun()
            
            q_fin = f"SELECT * FROM financeiro WHERE mes LIKE '%{mes_busca}%'" if mes_busca else "SELECT * FROM financeiro"
            st.dataframe(pd.read_sql_query(q_fin, sqlite3.connect(DB_PATH)), use_container_width=True)
        tab_idx += 1

    # --- ABA: AUDITORIA (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🕵️ Auditoria e Rastreabilidade")
            mes_atual_padrao = datetime.now().strftime("%m/%Y")
            filtro_mes_aud = st.text_input("🔍 Filtrar por Mês/Ano", value=mes_atual_padrao)
            
            q_aud = f"SELECT * FROM auditoria WHERE data_hora LIKE '%{filtro_mes_aud}%' ORDER BY id DESC" if filtro_mes_aud else "SELECT * FROM auditoria ORDER BY id DESC"
            df_auditoria = pd.read_sql_query(q_aud, sqlite3.connect(DB_PATH))
            if df_auditoria.empty:
                st.info(f"Nenhum registro para '{filtro_mes_aud}'.")
            else:
                st.dataframe(df_auditoria, use_container_width=True)
