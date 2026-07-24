import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import urllib.parse
import base64

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

# --- BANCO DE DADOS E MIGRAÇÕES ---
DB_PATH = "ad_monitoramento.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS empresas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, cnpj TEXT, endereco TEXT, telefone TEXT, responsavel TEXT)''')
    try:
        c.execute("ALTER TABLE empresas ADD COLUMN servicos TEXT DEFAULT 'Ambos (Furto/Roubo + Monitoramento)'")
        conn.commit()
    except sqlite3.OperationalError:
        pass
        
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
    usuario = st.session_state.get('nome_empresa', 'Sistema')
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    execute_query("INSERT INTO auditoria (data_hora, acao, modulo, detalhes, usuario) VALUES (?,?,?,?,?)", 
                  (agora, acao, modulo, detalhes, usuario))

# --- GERADOR DE RELATÓRIO HTML ---
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

# --- CONTROLE DE SESSÃO SEGURO (PRIMEIRO DE TUDO) ---
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
                    res = fetch_data("SELECT nome FROM empresas WHERE nome=? AND cnpj=?", (user, senha))
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
            st.query_params.clear()
            st.rerun()
        st.markdown("---")
        st.markdown("### 🛡️ Missão AD")
        st.markdown("**Foco total na segurança, agilidade e comprometimento.** Nossa missão é garantir proteção máxima e resposta rápida para a nossa frota e a de nossos parceiros.")

    abas = ["👤 Clientes", "📖 Relatórios"]
    if st.session_state.is_admin:
        abas = ["🚨 Central 24h", "👤 Clientes", "📖 Relatórios", "🏢 Empresas", "💰 Financeiro", "🕵️ Auditoria"]
        
    tabs = st.tabs(abas)
    tab_idx = 0

    # --- ABA: OPERAÇÃO 24H (SÓ ADMIN) ---
    if st.session_state.is_admin:
        with tabs[tab_idx]:
            st.header("🚨 Central de Operações e Ocorrências 24h")
            busca_op = st.text_input("🔍 Buscar veículo (Digite Nome, Placa ou CPF)", key="busca_op_input")
            
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
                        tipo_servico = st.radio("📋 **Ação na Central:**", ["Abertura de Furto/Roubo", "Monitoramento Técnico"], horizontal=True)
                        
                        if tipo_servico == "Abertura de Furto/Roubo":
                            with st.form("form_furto", clear_on_submit=True):
                                st.markdown("<h3 style='color: #8b0000;'>Abertura de Furto/Roubo (Início Automático)</h3>", unsafe_allow_html=True)
                                tipo_oc = st.selectbox("Natureza", ["Furto", "Roubo"])
                                local_oc = st.text_input("Localização do Fato")
                                desc_oc = st.text_area("Descrição / Dinâmica")
                                st.info("ℹ️ Status inicial configurado automaticamente como: EM ANDAMENTO.")
                                
                                if st.form_submit_button("Salvar Ocorrência"):
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (?,?,?,?,?,?,?)", 
                                              (agora, info_veic['nome'], placa_sel, tipo_oc, "EM ANDAMENTO", f"Local: {local_oc} | {desc_oc}", info_veic['empresa']))
                                    registrar_auditoria("Registro", "Operação", f"Ocorrência de {tipo_oc} INICIADA para {placa_sel}")
                                    st.session_state["busca_op_input"] = ""
                                    st.success(f"Salvo e enviado para relatórios como EM ANDAMENTO!")
                                    st.rerun()
                        
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
                                    st.session_state["busca_op_input"] = ""
                                    st.success("Salvo com sucesso!")
                                    st.rerun()
                else:
                    st.warning("Nenhum veículo encontrado com este termo.")
        tab_idx += 1

    # --- ABA: CLIENTES E FROTAS ---
    with tabs[tab_idx]:
        st.header("👤 Gerenciamento de Clientes (Frotas e Veículos)")
        
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
                st.download_button(label="📥 Baixar Base de Clientes (CSV Inteligente)", data=df_export.to_csv(index=False).encode('utf-8'), file_name="Base_Clientes.csv", mime="text/csv")
                
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
                tipo_inclusao = st.radio("Como deseja cadastrar?", ["📝 Cadastrar Cliente e Veículo Novos", "🚗 Adicionar Veículo a um Cliente Existente"], horizontal=True)
                
                if tipo_inclusao == "📝 Cadastrar Cliente e Veículo Novos":
                    st.subheader("Cadastro de Novo Cliente")
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
                        if st.form_submit_button("Salvar Novo Cliente"):
                            if nome and placa:
                                agora = datetime.now().strftime('%d/%m/%Y %H:%M')
                                execute_query("INSERT INTO clientes (nome, documento, endereco, telefone, tipo_veic, placa, modelo, cor, empresa, status, ultima_atualizacao) VALUES (?,?,?,?,?,?,?,?,?,'Ativo',?)", 
                                          (nome, doc, end, tel, tipo, placa, mod, cor, emp, agora))
                                registrar_auditoria("Cadastro", "Clientes", f"Cliente {nome} adicionado na pasta {emp}.")
                                st.session_state.acao_clientes = "Listar"
                                st.rerun()
                            else:
                                st.error("Nome e Placa são obrigatórios.")
                                
                elif tipo_inclusao == "🚗 Adicionar Veículo a um Cliente Existente":
                    if not df_clientes.empty:
                        lista_nomes_unicos = df_clientes['nome'].unique()
                        cli_sel_vinc = st.selectbox("Selecione o Cliente Existente para vincular o novo veículo:", [""] + list(lista_nomes_unicos))
                        
                        if cli_sel_vinc:
                            dados_cli_existente = df_clientes[df_clientes['nome'] == cli_sel_vinc].iloc[0]
                            st.info(f"Vincular novo veículo ao cliente: **{dados_cli_existente['nome']}** (Documento: {dados_cli_existente['documento']}) - Empresa: {dados_cli_existente['empresa']}")
                            
                            with st.form("novo_veiculo_vinculado", clear_on_submit=True):
                                c1, c2 = st.columns(2)
                                tipo = c1.selectbox("Tipo de Veículo", ["Carro", "Moto", "Caminhão", "Outro"])
                                placa = c2.text_input("Placa da Nova Frota *")
                                mod = c1.text_input("Modelo")
                                cor = c2.text_input("Cor")
                                if st.form_submit_button("Salvar Veículo Adicional"):
                                    if placa:
                                        agora = datetime.now().strftime('%d/%m/%Y %H:%M')
                                        execute_query("INSERT INTO clientes (nome, documento, endereco, telefone, tipo_veic, placa, modelo, cor, empresa, status, ultima_atualizacao) VALUES (?,?,?,?,?,?,?,?,?,'Ativo',?)", 
                                                  (dados_cli_existente['nome'], dados_cli_existente['documento'], dados_cli_existente['endereco'], dados_cli_existente['telefone'], tipo, placa, mod, cor, dados_cli_existente['empresa'], agora))
                                        registrar_auditoria("Cadastro", "Frotas", f"Veículo {placa} vinculado ao cliente {dados_cli_existente['nome']}.")
                                        st.session_state.acao_clientes = "Listar"
                                        st.rerun()
                                    else:
                                        st.error("A Placa é obrigatória.")
                    else:
                        st.warning("Nenhum cliente cadastrado ainda para vincular veículos.")
                            
        elif acao_clientes == "Importação em Lote":
            st.info("📥 Funcionalidade de Importação em Lote (CSV) disponível em breve.")
            
        elif acao_clientes in ["Editar", "Excluir"]:
            busca = st.text_input("🔍 Buscar Cliente na Lista (Nome, Placa ou CPF):", key="busca_cli_input")
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
                                    st.session_state["busca_cli_input"] = "" 
                                    st.session_state.acao_clientes = "Listar"
                                    st.rerun()
                        
                        elif acao_clientes == "Excluir":
                            st.warning(f"Tem certeza que deseja excluir o cliente/veículo **{dados_c['nome']} (Placa: {dados_c['placa']})**?")
                            if st.button("🗑️ Excluir Registro (Irreversível)"):
                                execute_query("DELETE FROM clientes WHERE id=?", (id_sel,))
                                registrar_auditoria("Exclusão", "Clientes", f"Cliente ID {id_sel} excluído.")
                                st.session_state["busca_cli_input"] = ""
                                st.session_state.acao_clientes = "Listar"
                                st.rerun()
                else:
                    st.warning("Nenhum cliente encontrado com esse termo.")
    tab_idx += 1

    # --- ABA: RELATÓRIOS ---
    with tabs[tab_idx]:
        st.header("📖 Relatórios Operacionais")
        
        if st.session_state.is_admin:
            servico_atual = "Ambos (Furto/Roubo + Monitoramento)"
        else:
            res_servico = fetch_data("SELECT servicos FROM empresas WHERE nome=?", (st.session_state.nome_empresa,))
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
                    
                    conn = sqlite3.connect(DB_PATH)
                    q_fr = "SELECT * FROM historico WHERE tipo IN ('Furto', 'Roubo')"
                    p_list_fr = []
                    if not st.session_state.is_admin:
                        q_fr += " AND empresa=?"
                        p_list_fr.append(st.session_state.nome_empresa)
                    if b_fr:
                        q_fr += " AND (lower(cliente) LIKE ? OR lower(placa) LIKE ?)"
                        p_list_fr.extend([f"%{b_fr.lower()}%", f"%{b_fr.lower()}%"])
                    if p_fr:
                        q_fr += " AND data_hora LIKE ?"
                        p_list_fr.append(f"%{p_fr}%")
                    q_fr += " ORDER BY id DESC"
                    
                    res_fr = fetch_data(q_fr, tuple(p_list_fr))
                    conn.close()
                    
                    if res_fr:
                        df_fr = pd.DataFrame(res_fr)
                        st.dataframe(df_fr[['id', 'data_hora', 'cliente', 'placa', 'tipo', 'status']], use_container_width=True)
                        
                        st.markdown("### 🔎 Ficha e Finalização de Ocorrência")
                        lista_sel_fr = [f"{h['id']} - {h['placa']} ({h['tipo']} - {h['status']})" for h in res_fr]
                        reg_sel_fr = st.selectbox("Selecione um atendimento para visualizar ou finalizar:", [""] + lista_sel_fr, key="sel_fr")
                        
                        if reg_sel_fr:
                            id_r = int(reg_sel_fr.split(" - ")[0])
                            dados_fr = next(item for item in res_fr if item["id"] == id_r)
                            
                            if st.button("❌ Fechar Ficha", key="fechar_fr"):
                                st.session_state["sel_fr"] = ""
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
                                with st.form(f"form_finalizar_reg_{id_r}"):
                                    st.write("🟢 **Finalizar Atendimento:**")
                                    desfecho = st.text_area("Informe o desfecho do caso (ex: Veículo recuperado com sucesso)")
                                    if st.form_submit_button("✅ Concluir e Finalizar Ocorrência"):
                                        novo_detalhe = dados_fr['detalhes'] + f" | DESFECHO: {desfecho}"
                                        execute_query("UPDATE historico SET status='FINALIZADO', detalhes=? WHERE id=?", (novo_detalhe, id_r))
                                        registrar_auditoria("Finalização", "Operação", f"Ocorrência ID {id_r} finalizada.")
                                        st.session_state["sel_fr"] = ""
                                        st.success("Ocorrência finalizada com sucesso!")
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
                    p_mon = col_m2.text_input("📅 Filtrar por Date (Monitoramento)", key="p_mon")
                    
                    conn = sqlite3.connect(DB_PATH)
                    q_mon = "SELECT * FROM historico WHERE tipo='Monitoramento'"
                    p_list_mon = []
                    if not st.session_state.is_admin:
                        q_mon += " AND empresa=?"
                        p_list_mon.append(st.session_state.nome_empresa)
                    if b_mon:
                        q_mon += " AND (lower(cliente) LIKE ? OR lower(placa) LIKE ?)"
                        p_list_mon.extend([f"%{b_mon.lower()}%", f"%{b_mon.lower()}%"])
                    if p_mon:
                        q_mon += " AND data_hora LIKE ?"
                        p_list_mon.append(f"%{p_mon}%")
                    q_mon += " ORDER BY id DESC"
                    
                    res_mon = fetch_data(q_mon, tuple(p_list_mon))
                    conn.close()
                    
                    if res_mon:
                        df_mon = pd.DataFrame(res_mon)
                        st.dataframe(df_mon[['id', 'data_hora', 'cliente', 'placa', 'tipo', 'status']], use_container_width=True)
                        
                        st.markdown("### 🔎 Ficha de Monitoramento")
                        lista_sel_mon = [f"{h['id']} - {h['placa']} ({h['data_hora']})" for h in res_mon]
                        reg_sel_mon = st.selectbox("Selecione um registro para visualizar:", [""] + lista_sel_mon, key="sel_mon")
                        
                        if reg_sel_mon:
                            id_m = int(reg_sel_mon.split(" - ")[0])
                            dados_mon = next(item for item in res_mon if item["id"] == id_m)
                            
                            if st.button("❌ Fechar Ficha", key="fechar_mon"):
                                st.session_state["sel_mon"] = ""
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

    # --- ABA: PARCEIROS (SÓ ADMIN) ---
    if st.session_state.is_admin and tab_idx < len(tabs):
        with tabs[tab_idx]:
            st.header("🏢 Gerenciamento de Empresas Parceiras")
            
            acao_parceiros = st.radio("Ação Empresas:", ["Listar", "Incluir Nova", "Editar", "Excluir"], horizontal=True)
            st.markdown("---")
            
            df_empresas = pd.read_sql_query("SELECT * FROM empresas", sqlite3.connect(DB_PATH))
            
            if acao_parceiros == "Listar":
                if not df_empresas.empty:
                    for _, emp in df_empresas.iterrows():
                        with st.expander(f"📁 Empresa: {emp['nome']}"):
                            st.write(f"**CNPJ/Senha:** {emp['cnpj']} | **Responsável:** {emp['responsavel']}")
                            st.write(f"**Telefone:** {emp['telefone']} | **Endereço:** {emp['endereco']}")
                            servico_vinculado = emp['servicos'] if 'servicos' in emp else "Ambos (Furto/Roubo + Monitoramento)"
                            st.write(f"**Pacote de Serviço:** {servico_vinculado}")
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
                    
                    if st.form_submit_button("Registrar Parceiro"):
                        if e_nome and e_cnpj:
                            execute_query("INSERT INTO empresas (nome, cnpj, endereco, telefone, responsavel, servicos) VALUES (?,?,?,?,?,?)", (e_nome, e_cnpj, e_end, e_tel, e_resp, e_servicos))
                            registrar_auditoria("Cadastro", "Parceiros", f"Empresa {e_nome} criada com pacote: {e_servicos}.")
                            st.rerun()
                        else:
                            st.error("Nome e CNPJ são obrigatórios.")
                            
            elif acao_parceiros in ["Editar", "Excluir"]:
                res_emp = fetch_data("SELECT * FROM empresas")
                if res_emp:
                    lista_opcoes_e = [f"{e['id']} - {e['nome']}" for e in res_emp]
                    emp_selecionada = st.selectbox("🔍 Selecione a Empresa na lista (ou digite para buscar):", [""] + lista_opcoes_e, key="sel_emp_edit")
                    
                    if emp_selecionada:
                        id_emp = int(emp_selecionada.split(" - ")[0])
                        dados_e = next(item for item in res_emp if item["id"] == id_emp)
                        
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

                                if st.form_submit_button("💾 Salvar Alterações"):
                                    execute_query("UPDATE empresas SET nome=?, responsavel=?, telefone=?, endereco=?, servicos=? WHERE id=?", (ne_nome, ne_resp, ne_tel, ne_end, ne_servicos, id_emp))
                                    registrar_auditoria("Edição", "Parceiros", f"Parceiro ID {id_emp} alterado. Serviço: {ne_servicos}")
                                    st.rerun()
                        
                        elif acao_parceiros == "Excluir":
                            st.warning(f"Tem certeza que deseja excluir a empresa **{dados_e['nome']}**?")
                            if st.button("🗑️ Excluir Parceiro"):
                                execute_query("DELETE FROM empresas WHERE id=?", (id_emp,))
                                registrar_auditoria("Exclusão", "Parceiros", f"Parceiro ID {id_emp} excluído.")
                                st.rerun()
                else:
                    st.warning("Nenhuma empresa encontrada.")
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
