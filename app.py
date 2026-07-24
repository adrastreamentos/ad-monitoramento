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
    pdf.cell(200, 10, txt=f"Relatório Oficial de Ocorrências - AD Rastreamento", ln=True, align='C')
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

    abas = ["👤 Clientes e Frotas", "📖 Histórico (PDF)"]
    if st.session_state.is_admin:
        abas = ["🚨 Operação 24h", "👤 Clientes e Frotas", "📖 Histórico (PDF)", "🏢 Parceiros", "💰 Financeiro", "🕵️ Auditoria"]
        
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
                        tipo_servico = st.radio("📋 **Selecione a ação na Central:**", ["Abertura de Furto/Roubo", "Finalizar Ocorrência Ativa", "Monitoramento Técnico"], horizontal=True)
                        
                        # 1. Abertura Furto/Roubo (Status Automático)
                        if tipo_servico == "Abertura de Furto/Roubo":
                            with st.form("form_furto", clear_on_submit=True):
                                st.markdown("<h3 style='color: #8b0000;'>Abertura de Furto/Roubo (Início de Atendimento)</h3>", unsafe_allow_html=True)
                                tipo_oc = st.selectbox("Natureza", ["Furto", "Roubo"])
                                local_oc = st.text_input("Localização do Fato")
                                desc_oc = st.text_area("Descrição / Dinâmica do Ocorrido")
                                st.info("ℹ️ Ao salvar, o status desta ocorrência constará automaticamente como EM ANDAMENTO no histórico.")
                                
                                if st.form_submit_button("Salvar Ocorrência"):
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, tipo_oc, "EM ANDAMENTO", f"Local: {local_oc} | {desc_oc}", info_veic['empresa']))
                                    registrar_auditoria("Registro", "Operação", f"Ocorrência de {tipo_oc} INICIADA para {placa_sel}")
                                    st.success(f"Ocorrência salva com sucesso! Tela sendo limpa...")
                                    st.rerun()
                        
                        # 2. Finalizar Ocorrência (Mudar Status)
                        elif tipo_servico == "Finalizar Ocorrência Ativa":
                            pendentes = fetch_data("SELECT * FROM historico WHERE placa=? AND status='EM ANDAMENTO'", (placa_sel,))
                            if pendentes:
                                with st.form("form_finalizar", clear_on_submit=True):
                                    st.markdown("<h3 style='color: #8b0000;'>Finalizar Ocorrência de Furto/Roubo</h3>", unsafe_allow_html=True)
                                    id_pendente = pendentes[0]['id']
                                    st.write(f"**Ocorrência Pendente:** {pendentes[0]['tipo']} registrada em {pendentes[0]['data_hora']}")
                                    conclusao_oc = st.text_area("Desfecho do Atendimento (Recuperado, etc.)")
                                    
                                    if st.form_submit_button("Finalizar Ocorrência"):
                                        novo_detalhe = pendentes[0]['detalhes'] + f" | DESFECHO: {conclusao_oc}"
                                        execute_query("UPDATE historico SET status='FINALIZADO', detalhes=? WHERE id=?", (novo_detalhe, id_pendente))
                                        registrar_auditoria("Atualização", "Operação", f"Ocorrência ID {id_pendente} FINALIZADA.")
                                        st.success("Ocorrência Finalizada! Tela sendo limpa...")
                                        st.rerun()
                            else:
                                st.warning("Não há ocorrências em andamento para este veículo.")
                        
                        # 3. Monitoramento Técnico
                        elif tipo_servico == "Monitoramento Técnico":
                            with st.form("form_monitoramento", clear_on_submit=True):
                                st.markdown("<h3 style='color: #4a0e4e;'>Monitoramento Técnico</h3>", unsafe_allow_html=True)
                                evento_mon = st.selectbox("Evento Detectado", ["Cerca Virtual", "Desconexão de Bateria", "Falta de Comunicação", "Outros"])
                                acao_mon = st.text_area("Ação Tomada pela Central")
                                if st.form_submit_button("Salvar Monitoramento"):
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, "Monitoramento", "FINALIZADO", f"Evento: {evento_mon} | Ação: {acao_mon}", info_veic['empresa']))
                                    registrar_auditoria("Registro", "Monitoramento", f"Evento de {evento_mon} para {placa_sel}")
                                    st.success("Monitoramento salvo com sucesso! Tela sendo limpa...")
                                    st.rerun()
        tab_idx += 1

    # --- ABA: CLIENTES E FROTAS ---
    with tabs[tab_idx]:
        st.header("👤 Gestão de Clientes e Frotas")
        
        empresas_disp = fetch_data("SELECT nome FROM empresas")
        opcoes_emp = [e['nome'] for e in empresas_disp] if st.session_state.is_admin else [st.session_state.nome_empresa]
        
        q_clientes = "SELECT * FROM clientes" if st.session_state.is_admin else f"SELECT * FROM clientes WHERE empresa='{st.session_state.nome_empresa}'"
        df_clientes = pd.read_sql_query(q_clientes, sqlite3.connect(DB_PATH))

        # EXPORTAÇÃO INTELIGENTE (CSV) - Apenas dados necessários
        if not df_clientes.empty:
            df_export = df_clientes[['nome', 'documento', 'endereco', 'telefone', 'tipo_veic', 'placa', 'modelo', 'cor']]
            df_export.columns = ['Nome', 'CPF/CNPJ', 'Endereço', 'Telefone', 'Tipo de Veículo', 'Placa', 'Modelo', 'Cor']
            st.download_button(label="📥 Baixar Base de Clientes (CSV Inteligente)", data=df_export.to_csv(index=False).encode('utf-8'), file_name="Base_Clientes_AD.csv", mime="text/csv")
            st.markdown("---")

        # CADASTRO DE CLIENTE
        with st.expander("➕ Cadastrar Novo Cliente"):
            if not opcoes_emp:
                st.error("Nenhuma empresa parceira cadastrada! Cadastre a empresa primeiro na aba de Parceiros.")
            else:
                with st.form("novo_cliente", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    nome = c1.text_input("Nome do Cliente *")
                    doc = c2.text_input("CPF/CNPJ")
                    end = c1.text_input("Endereço")
                    tel = c2.text_input("Telefone")
                    emp = c1.selectbox("Empresa Proprietária (Pasta) *", opcoes_emp)
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
                            st.success(f"Cliente cadastrado com sucesso! A tela foi limpa e o registro enviado para a pasta da {emp}.")
                            st.rerun()
                        else:
                            st.error("Nome e Placa são obrigatórios.")

        st.subheader("📁 Organização em Pastas (Por Parceiro)")
        if not df_clientes.empty:
            empresas_ativas = df_clientes['empresa'].unique()
            
            for emp_ativa in empresas_ativas:
                with st.expander(f"📂 Empresa: {emp_ativa}"):
                    df_emp = df_clientes[df_clientes['empresa'] == emp_ativa]
                    st.dataframe(df_emp[['id', 'nome', 'documento', 'placa', 'modelo', 'status']], use_container_width=True)
                    
                    st.markdown(f"**🛠️ Incluir / Editar / Excluir Cliente ({emp_ativa}):**")
                    lista_cli_emp = df_emp['id'].astype(str) + " - " + df_emp['nome'] + " (" + df_emp['placa'] + ")"
                    cli_sel_pasta = st.selectbox(f"Selecione um cliente para edição:", [""] + list(lista_cli_emp), key=f"sel_cli_{emp_ativa}")
                    
                    if cli_sel_pasta:
                        id_cli_pasta = int(cli_sel_pasta.split(" - ")[0])
                        dados_c = df_emp[df_emp['id'] == id_cli_pasta].iloc[0]
                        
                        with st.form(f"form_edit_cli_{id_cli_pasta}", clear_on_submit=True):
                            en_nome = st.text_input("Nome", value=dados_c['nome'])
                            en_placa = st.text_input("Placa", value=dados_c['placa'])
                            en_status = st.selectbox("Status", ["Ativo", "Inativo"], index=0 if dados_c['status']=='Ativo' else 1)
                            
                            col_ba, col_bb = st.columns(2)
                            if col_ba.form_submit_button("💾 Salvar Alterações"):
                                execute_query("UPDATE clientes SET nome=?, placa=?, status=? WHERE id=?", (en_nome, en_placa, en_status, id_cli_pasta))
                                registrar_auditoria("Edição", "Clientes", f"Cliente ID {id_cli_pasta} alterado.")
                                st.success("Atualizado com sucesso! Tela limpa.")
                                st.rerun()
                            if col_bb.form_submit_button("🗑️ Excluir Cliente"):
                                execute_query("DELETE FROM clientes WHERE id=?", (id_cli_pasta,))
                                registrar_auditoria("Exclusão", "Clientes", f"Cliente ID {id_cli_pasta} excluído.")
                                st.warning("Cliente excluído! Tela limpa.")
                                st.rerun()
        else:
            st.info("Nenhum cliente cadastrado em pastas no momento.")
        
        if not st.session_state.is_admin:
            st.markdown("---")
            st.markdown("### 🚑 Apoio da Central")
            texto_wpp = f"🚨 *ATENDIMENTO INDIRETO* 🚨\n🏢 Parceiro acionando: {st.session_state.nome_empresa}\n⚠️ Precisamos de apoio!"
            url_wpp = f"https://wa.me/5584999305771?text={urllib.parse.quote(texto_wpp)}"
            st.markdown(f'<a href="{url_wpp}" target="_blank"><button style="background-color:#25D366; color:white; padding:10px; border-radius:5px; border:none; font-weight:bold;">🚨 Acionar Central via WhatsApp</button></a>', unsafe_allow_html=True)
    tab_idx += 1

    # --- ABA: HISTÓRICO & PDF ---
    with tabs[tab_idx]:
        st.header("📖 Histórico Operacional (Emissão de PDF)")
        
        col_f1, col_f2 = st.columns(2)
        filtro_busca_hist = col_f1.text_input("🔍 Filtrar por Placa, Nome ou CPF")
        filtro_periodo = col_f2.text_input("📅 Filtrar por Período / Data")
        
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
        df_hist = pd.read_sql_query(query_h, conn, params=params_h)
        conn.close()
        
        st.dataframe(df_hist, use_container_width=True)
        
        if st.session_state.is_admin and not df_hist.empty:
            with st.expander("⚙️ Excluir Registro do Histórico (Admin)"):
                id_del_hist = st.selectbox("Selecione o ID do Histórico para remover:", [""] + list(df_hist['id'].astype(str)))
                if id_del_hist and st.button("🗑️ Excluir Registro Selecionado"):
                    execute_query("DELETE FROM historico WHERE id=?", (int(id_del_hist),))
                    registrar_auditoria("Exclusão", "Histórico", f"Registro ID {id_del_hist} removido.")
                    st.success("Removido com sucesso!")
                    st.rerun()

        if not df_hist.empty:
            if FPDF is not None:
                pdf_bytes = gerar_pdf_historico(df_hist, st.session_state.nome_empresa)
                if pdf_bytes:
                    st.download_button(label="📄 Baixar Relatório Oficial (Exclusivo PDF)", data=pdf_bytes, file_name=f"Relatorio_Ocorrencias_{st.session_state.nome_empresa}.pdf", mime="application/pdf")
            else:
                st.error("⚠️ Biblioteca 'fpdf' ausente no servidor. O PDF não pôde ser gerado.")
    tab_idx += 1

    # --- ABA: PARCEIROS (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🏢 Gestão de Empresas Parceiras")
            
            with st.expander("➕ Cadastrar Novo Parceiro"):
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
                            st.success(f"Empresa {e_nome} criada com sucesso! Formulário limpo.")
                            st.rerun()
                        else:
                            st.error("Nome e CNPJ são obrigatórios.")

            st.markdown("---")
            st.subheader("📁 Organização em Pastas (Parceiros)")
            df_empresas = pd.read_sql_query("SELECT * FROM empresas", sqlite3.connect(DB_PATH))
            
            if not df_empresas.empty:
                for _, emp in df_empresas.iterrows():
                    with st.expander(f"📂 Empresa: {emp['nome']}"):
                        st.write(f"**CNPJ/Senha:** {emp['cnpj']} | **Responsável:** {emp['responsavel']}")
                        st.write(f"**Telefone:** {emp['telefone']} | **Endereço:** {emp['endereco']}")
                        
                        id_emp = emp['id']
                        st.markdown("**🛠️ Editar / Excluir Parceiro:**")
                        with st.form(f"form_edit_emp_{id_emp}", clear_on_submit=True):
                            ne_nome = st.text_input("Nome", value=emp['nome'])
                            ne_resp = st.text_input("Responsável", value=emp['responsavel'])
                            ne_tel = st.text_input("Telefone", value=emp['telefone'])
                            ne_end = st.text_input("Endereço", value=emp['endereco'])
                            
                            c_b1, c_b2 = st.columns(2)
                            if c_b1.form_submit_button("💾 Salvar Alterações"):
                                execute_query("UPDATE empresas SET nome=?, responsavel=?, telefone=?, endereco=? WHERE id=?", (ne_nome, ne_resp, ne_tel, ne_end, id_emp))
                                registrar_auditoria("Edição", "Parceiros", f"Parceiro ID {id_emp} alterado.")
                                st.success("Parceiro atualizado! Tela limpa.")
                                st.rerun()
                            if c_b2.form_submit_button("🗑️ Excluir Parceiro"):
                                execute_query("DELETE FROM empresas WHERE id=?", (id_emp,))
                                registrar_auditoria("Exclusão", "Parceiros", f"Parceiro ID {id_emp} excluído.")
                                st.warning("Parceiro excluído! Tela limpa.")
                                st.rerun()
            else:
                st.info("Nenhum parceiro cadastrado.")
        tab_idx += 1

    # --- ABA: FINANCEIRO (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("💰 Controle Financeiro de Parceiros")
            mes_busca = st.text_input("🔍 Filtrar por Mês")
            
            with st.expander("➕ Lançar Faturamento"):
                with st.form("form_fin", clear_on_submit=True):
                    f_mes = st.text_input("Mês de Referência (Ex: 07/2026)")
                    f_emp = st.selectbox("Empresa", [e['nome'] for e in fetch_data("SELECT nome FROM empresas")])
                    f_fat = st.number_input("Valor Faturado (R$)", min_value=0.0, format="%.2f")
                    f_rec = st.number_input("Valor Recebido/Pago (R$)", min_value=0.0, format="%.2f")
                    f_stat = st.selectbox("Status", ["Pendente", "Pago Parcial", "Pago Integral"])
                    if st.form_submit_button("Salvar Lançamento"):
                        execute_query("INSERT INTO financeiro (mes, empresa, faturado, recebido, status) VALUES (?,?,?,?,?)", 
                                      (f_mes, f_emp, f_fat, f_rec, f_stat))
                        st.success("Lançamento salvo com sucesso!")
                        st.rerun()
            
            q_fin = f"SELECT * FROM financeiro WHERE mes LIKE '%{mes_busca}%'" if mes_busca else "SELECT * FROM financeiro"
            df_fin = pd.read_sql_query(q_fin, sqlite3.connect(DB_PATH))
            st.dataframe(df_fin, use_container_width=True)
        tab_idx += 1

    # --- ABA: AUDITORIA (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🕵️ Auditoria e Rastreabilidade do Sistema")
            
            mes_atual_padrao = datetime.now().strftime("%m/%Y")
            filtro_mes_aud = st.text_input("🔍 Filtrar Auditoria por Mês/Ano", value=mes_atual_padrao)
            
            q_aud = f"SELECT * FROM auditoria WHERE data_hora LIKE '%{filtro_mes_aud}%' ORDER BY id DESC" if filtro_mes_aud else "SELECT * FROM auditoria ORDER BY id DESC"
            df_auditoria = pd.read_sql_query(q_aud, sqlite3.connect(DB_PATH))
            
            if df_auditoria.empty:
                st.info(f"Nenhum registro de auditoria encontrado para o período '{filtro_mes_aud}'.")
            else:
                st.dataframe(df_auditoria, use_container_width=True)
