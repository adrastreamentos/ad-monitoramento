import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import urllib.parse
import base64
import psycopg2
from psycopg2.extras import RealDictCursor
import io
import os
import hashlib
import uuid
import re
import altair as alt

# --- CONFIGURAÇÕES DA PÁGINA E IDENTIDADE VISUAL ---
st.set_page_config(page_title="Central de Operações", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #fdfdfd; }
    h1, h2, h3 { color: #4a0e4e; margin-top: 0px; margin-bottom: 10px; }
    .stButton>button { background-color: #8b0000; color: white; font-weight: bold; border-radius: 6px; border: none; transition: 0.3s; }
    .stButton>button:hover { background-color: #4a0e4e; color: white; border: 1px solid #8b0000; }
    div[data-testid="stSidebar"] { background-color: #4a0e4e; }
    div[data-testid="stSidebar"] * { color: white; }
    
    /* --- MENU VISUALMENTE SEPARADO --- */
    div[role="radiogroup"] { 
        justify-content: center; 
        gap: 15px; 
        padding: 15px; 
        background-color: #f7f7f7; 
        border-radius: 8px;
        border-bottom: 4px solid #4a0e4e;
    }
    
    div[role="radiogroup"] > label {
        background-color: #ffffff;
        border: 2px solid #e0e0e0;
        padding: 8px 18px;
        border-radius: 8px;
        cursor: pointer;
        transition: 0.2s;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    div[role="radiogroup"] > label:hover {
        border-color: #4a0e4e;
        background-color: #fafafa;
    }
    
    div[role="radiogroup"] > label[data-checked="true"] {
        border-color: #8b0000;
        background-color: #fff5f5;
    }
    
    div[data-testid="stExpander"] { border-left: 4px solid #4a0e4e; }
    
    .ficha-box { border: 2px solid #4a0e4e; padding: 20px; border-radius: 10px; background-color: #fafafa; margin-top: 15px;}
    
    /* Títulos refinados para o Dashboard */
    .dash-title { color: #4a0e4e; font-size: 20px; font-weight: 600; text-align: center; border-bottom: 2px solid #eee; padding-bottom: 10px; margin-bottom: 15px; }
    .dash-legend { font-size: 14px; color: #555; display: flex; justify-content: space-between; padding: 5px 10px; border-bottom: 1px solid #f0f0f0; }
</style>
""", unsafe_allow_html=True)

# --- CRIPTOGRAFIA DE SENHAS (HASH) E SESSÃO ---
def hash_senha(senha):
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()

if 'session_uuid' not in st.session_state:
    st.session_state.session_uuid = str(uuid.uuid4()).split('-')[0].upper()

# --- CONEXÃO COM SUPABASE (POSTGRESQL) OTIMIZADA PARA VELOCIDADE ---
@st.cache_resource(ttl=3600)
def get_db_connection():
    try:
        return psycopg2.connect(st.secrets["SUPABASE_URL"])
    except Exception as e:
        st.error(f"Erro de conexão com a Nuvem (Supabase): {e}")
        st.stop()

def get_conn_fast():
    conn = get_db_connection()
    if conn.closed:
        st.cache_resource.clear()
        conn = get_db_connection()
    return conn

@st.cache_resource(show_spinner=False)
def init_db():
    conn = get_conn_fast()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS empresas (id SERIAL PRIMARY KEY, nome TEXT, cnpj TEXT, endereco TEXT, telefone TEXT, responsavel TEXT, servicos TEXT DEFAULT 'Ambos (Furto/Roubo + Monitoramento)', valor_veiculo REAL DEFAULT 3.00, dia_vencimento INTEGER DEFAULT 10, status_pagamento TEXT DEFAULT 'Pendente', valor_pago REAL DEFAULT 0.00, logo_binario BYTEA)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico_faturas (id SERIAL PRIMARY KEY, mes_ref TEXT, empresa TEXT, total_veiculos INTEGER, valor_unitario REAL, valor_fatura_calculada REAL, valor_pago REAL, status TEXT, data_pagamento TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notificacoes (id SERIAL PRIMARY KEY, data_hora TEXT, empresa TEXT, mensagem TEXT, lida BOOLEAN DEFAULT FALSE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS aceites_lgpd (id SERIAL PRIMARY KEY, empresa TEXT, data_hora TEXT, ip_aceite TEXT DEFAULT 'Sistema Web', hash_assinatura TEXT)''')

    try:
        c.execute("ALTER TABLE empresas ADD COLUMN IF NOT EXISTS senha TEXT;")
        c.execute("ALTER TABLE aceites_lgpd ADD COLUMN IF NOT EXISTS hash_assinatura TEXT;")
        c.execute("ALTER TABLE empresas ADD COLUMN IF NOT EXISTS valor_pago REAL DEFAULT 0.00;")
        c.execute("ALTER TABLE empresas ADD COLUMN IF NOT EXISTS logo_binario BYTEA;")
        c.execute("ALTER TABLE historico_faturas ADD COLUMN IF NOT EXISTS valor_fatura_calculada REAL DEFAULT 0.00;")
        c.execute("ALTER TABLE empresas ADD COLUMN IF NOT EXISTS email TEXT;")
        conn.commit()
    except Exception:
        conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS clientes (id SERIAL PRIMARY KEY, nome TEXT, documento TEXT, endereco TEXT, telefone TEXT, empresa TEXT, status TEXT DEFAULT 'Ativo')''')
    c.execute('''CREATE TABLE IF NOT EXISTS veiculos (id SERIAL PRIMARY KEY, cliente_id INTEGER REFERENCES clientes(id) ON DELETE CASCADE, tipo_veic TEXT, placa TEXT, modelo TEXT, cor TEXT)''')
    
    try:
        c.execute("ALTER TABLE veiculos ADD COLUMN IF NOT EXISTS info_chip TEXT DEFAULT '';")
        conn.commit()
    except Exception:
        conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS historico (id SERIAL PRIMARY KEY, data_hora TEXT, cliente TEXT, placa TEXT, tipo TEXT, status TEXT, detalhes TEXT, empresa TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS auditoria (id SERIAL PRIMARY KEY, data_hora TEXT, acao TEXT, modulo TEXT, detalhes TEXT, usuario TEXT)''')
    
    c.execute('''CREATE INDEX IF NOT EXISTS idx_veiculos_placa ON veiculos(placa)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_clientes_doc ON clientes(documento)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_clientes_nome ON clientes(nome)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_historico_placa ON historico(placa)''')
    
    conn.commit()

@st.cache_data(ttl=2, show_spinner=False)
def fetch_data(query, params=()):
    conn = get_conn_fast()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute(query, params)
    data = c.fetchall()
    return data

@st.cache_data(ttl=600, show_spinner=False)
def fetch_logo_cached(empresa_nome):
    try:
        conn = get_conn_fast()
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("SELECT logo_binario FROM empresas WHERE nome=%s", (empresa_nome,))
        res = c.fetchone()
        if res and res.get('logo_binario'):
            return bytes(res['logo_binario'])
    except Exception:
        pass
    return None

def execute_query(query, params=()):
    conn = get_conn_fast()
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    st.cache_data.clear()

init_db()

# --- FUNÇÕES ÚTEIS E REGRAS DE NEGÓCIO ---
def get_horario_brasil():
    fuso_br = timezone(timedelta(hours=-3))
    return datetime.now(fuso_br)

def get_horario_brasil_str():
    return get_horario_brasil().strftime("%d/%m/%Y %H:%M:%S")

def registrar_auditoria(acao, modulo, detalhes, empresa_rel=None):
    if st.session_state.get('is_admin'):
        usuario = "AD ADMIN"
    else:
        usuario = st.session_state.get('nome_empresa', 'Desconhecido')
    
    if empresa_rel:
        detalhes = f"{detalhes} | Alvo: {empresa_rel}"
        
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
    detalhes_texto = dados_relatorio['detalhes']
    assinatura_bloco = ""
    
    if "PROTOCOLO" in detalhes_texto or "RESOLUÇÃO" in detalhes_texto:
        assinatura_bloco = f"""
        <div style="margin-top: 30px; padding: 15px; background-color: #e8f5e9; border-left: 5px solid #2e7d32; border-radius: 5px;">
            <h4 style="color: #2e7d32; margin-top: 0;">🔐 Assinatura Digital e Validação</h4>
            <p style="margin: 0; font-size: 14px;">Este documento foi encerrado e validado de forma inalterável. Os registros de resolução e protocolos estão fixados na base de dados oficial (PostgreSQL).</p>
        </div>
        """

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
            <div class="field"><span class="label">Data e Hora de Abertura:</span> {dados_relatorio['data_hora']}</div>
            <div class="field"><span class="label">Cliente:</span> {dados_relatorio['cliente']}</div>
            <div class="field"><span class="label">Placa do Veículo:</span> {dados_relatorio['placa']}</div>
            <div class="field"><span class="label">Tipo de Ocorrência:</span> {dados_relatorio['tipo']}</div>
            <div class="field"><span class="label">Status Atual:</span> {dados_relatorio['status']}</div>
            <hr style="border: 0; border-top: 1px solid #ccc; margin: 20px 0;">
            <div class="field"><span class="label">Detalhes / Dinâmica / Desfecho:</span><br><p>{detalhes_texto}</p></div>
            {assinatura_bloco}
        </div>
        <div class="footer">
            Documento gerado automaticamente pela Central de Operações de Segurança AD Rastreamento Veicular.
        </div>
    </body>
    </html>
    """
    b64 = base64.b64encode(html_content.encode('utf-8')).decode("utf-8")
    return f'<a href="data:text/html;base64,{b64}" download="Relatorio_{dados_relatorio["placa"]}.html" target="_blank"><button style="background-color:#4a0e4e; color:white; padding:10px 15px; border-radius:5px; border:none; font-weight:bold; cursor:pointer;">📄 Baixar Relatório Oficial (HTML/PDF)</button></a>'

# --- BASE DE CONHECIMENTO (DIAGNÓSTICO TÉCNICO INTELIGENTE) ---
DIAGNOSTICOS_TECNICOS = {
    "Falta de Comunicação": {
        "diagnostico": "Identificamos uma alta incidência de perda de pacote de dados e falha de GPRS nos equipamentos.",
        "causa": "Problemas de cobertura local (zona de sombra), falha na antena interna do módulo, ou bloqueio temporário na linha do chip M2M pela operadora de telefonia.",
        "acao": "Realizar um teste de ping remoto (varredura de sinal) nos chips afetados. Caso os veículos operem sempre em regiões remotas, recomenda-se a substituição por chips Multi-Operadora (Roaming) para estabilizar a telemetria."
    },
    "Desconexão de Bateria": {
        "diagnostico": "Houve um pico de alertas de violação de alimentação principal ou queda crítica de tensão.",
        "causa": "O veículo pode ter sido levado a uma oficina sem aviso à central, a bateria do veículo apresenta desgaste acentuado (arriada), ou há uma tentativa suspeita de sabotagem do chicote do rastreador.",
        "acao": "Estabelecer uma rotina de contato imediato com o condutor/gestor da frota assim que o evento for disparado. Se não houver manutenção autorizada em curso, abrir protocolo de segurança urgente e agendar revisão de instalação."
    },
    "Cerca Virtual": {
        "diagnostico": "Alto volume de notificações por evasão de perímetro geográfico ou quebra de rota.",
        "causa": "Uso indevido do veículo fora do horário comercial, desvio de rota por parte do condutor, ou raio da cerca configurado na plataforma em tamanho muito restrito/pequeno.",
        "acao": "Revisar as regras de roteirização diretamente com o dono da frota. Se o perímetro for oficial, recomenda-se uma advertência ou reorientação das políticas de frota junto aos motoristas."
    },
    "Transferência - Setor Financeiro": {
        "diagnostico": "Elevado número de chamados transferidos para tratativas de faturas, cobranças e bloqueios.",
        "causa": "Dificuldades dos clientes finais em localizar os boletos, dúvidas sobre mensalidades atrasadas ou pedidos de reativação de sinal após bloqueio por inadimplência.",
        "acao": "Recomendamos implementar réguas de cobrança automatizadas via WhatsApp/E-mail (ex: envios 5 e 2 dias antes do vencimento) para reduzir consideravelmente a sobrecarga humana no setor de suporte."
    },
    "Transferência - Setor Técnico": {
        "diagnostico": "Sobrecarga de chamados repassados para a equipe de suporte avançado e manutenção física.",
        "causa": "Clientes com dificuldades em manusear o aplicativo mobile, dúvidas de acesso, ou falhas intermitentes em equipamentos legados (rastreadores muito antigos precisando de recall).",
        "acao": "Criar pequenos vídeos tutoriais fáceis sobre o uso do App e disparar para a base. Para veículos reincidentes, agendar recall para troca preventiva de hardware."
    },
    "Furto": {
        "diagnostico": "Aumento direto nos índices de sinistro da frota monitorada.",
        "causa": "Exposição excessiva dos veículos em vias públicas sem vigilância durante horários e madrugadas de alta vulnerabilidade.",
        "acao": "Orientar o cliente a utilizar cercas virtuais noturnas rígidas e avaliar urgentemente a instalação de iscas de rádio-frequência (RF) ou rastreadores secundários autônomos."
    },
    "Roubo": {
        "diagnostico": "Elevação severa das ocorrências de roubo em trânsito (abordagem com veículo em movimento).",
        "causa": "Circulação em zonas de alta mancha criminal ou rotas de escoamento visadas por quadrilhas especializadas.",
        "acao": "Afinar a inteligência de bloqueio remoto (corte progressivo). Estudar o mapeamento da mancha criminal e redesenhar o trajeto dos motoristas nas zonas de risco."
    }
}

# --- CONTROLE DE SESSÃO SEGURO E LIMPEZA DE TELA ---
if 'logged_in' not in st.session_state:
    if st.query_params.get("logged_in") == "true":
        st.session_state.logged_in = True
        st.session_state.is_admin = (st.query_params.get("admin") == "true")
        st.session_state.nome_empresa = st.query_params.get("empresa", "")
        st.session_state.lgpd_aceito = True 
    else:
        st.session_state.logged_in = False
        st.session_state.is_admin = False
        st.session_state.nome_empresa = ""
        st.session_state.lgpd_aceito = False

if 'acao_clientes' not in st.session_state: st.session_state.acao_clientes = "Listar"
if 'num_veiculos_state' not in st.session_state: st.session_state.num_veiculos_state = 1
if 'rk' not in st.session_state: st.session_state.rk = 0 
if 'termo_busca_ativo' not in st.session_state: st.session_state.termo_busca_ativo = ""
if 'termo_cli_ativo' not in st.session_state: st.session_state.termo_cli_ativo = ""
if 'last_viewed_cli' not in st.session_state: st.session_state.last_viewed_cli = None
if 'link_transferencia' not in st.session_state: st.session_state.link_transferencia = None
if 'empresa_transferencia' not in st.session_state: st.session_state.empresa_transferencia = None
if 'mostrar_laudo' not in st.session_state: st.session_state.mostrar_laudo = False

chaves_necessarias = {
    'edit_cli': 0, 'rel_fr': 0, 'rel_mon': 0, 'edit_emp': 0, 'aud_del': 0, 'fin_pgto': 0, 'ficha_cli': 0, 'lgpd_cert': 0, 'dash_mes': 0
}

if 'reset_keys' not in st.session_state:
    st.session_state.reset_keys = chaves_necessarias.copy()
else:
    for chave, valor_padrao in chaves_necessarias.items():
        if chave not in st.session_state.reset_keys:
            st.session_state.reset_keys[chave] = valor_padrao

def limpar_tela():
    st.session_state.rk += 1
    st.session_state.termo_busca_ativo = ""
    st.session_state.termo_cli_ativo = ""
    st.session_state.last_viewed_cli = None
    st.session_state.link_transferencia = None
    st.session_state.empresa_transferencia = None
    st.session_state.mostrar_laudo = False
    for k in st.session_state.reset_keys:
        st.session_state.reset_keys[k] += 1

if 'flash_msg' in st.session_state:
    st.toast(st.session_state.flash_msg, icon="✅")
    del st.session_state.flash_msg

# ==========================================
# 1. TELA DE LOGIN
# ==========================================
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #4a0e4e;'>🛡️ Central de Operações de Segurança</h1>", unsafe_allow_html=True)
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
                    st.session_state.lgpd_aceito = True 
                    st.query_params["logged_in"] = "true"
                    st.query_params["admin"] = "true"
                    st.query_params["empresa"] = "AD RASTREAMENTO VEICULAR"
                    st.rerun()
                else:
                    senha_criptografada = hash_senha(senha)
                    res = fetch_data("SELECT nome, cnpj, senha FROM empresas WHERE nome=%s", (user,))
                    
                    if res:
                        emp_dados = res[0]
                        senha_salva = emp_dados.get('senha')
                        cnpj_salvo = emp_dados.get('cnpj')
                        
                        login_sucesso = False
                        
                        if senha_salva and senha_salva == senha_criptografada:
                            login_sucesso = True
                        elif not senha_salva:
                            if cnpj_salvo == senha:
                                execute_query("UPDATE empresas SET senha=%s WHERE nome=%s", (senha_criptografada, user))
                                login_sucesso = True
                            elif cnpj_salvo == senha_criptografada:
                                execute_query("UPDATE empresas SET senha=%s WHERE nome=%s", (senha_criptografada, user))
                                login_sucesso = True
                        
                        if login_sucesso:
                            st.session_state.logged_in = True
                            st.session_state.is_admin = False
                            st.session_state.nome_empresa = emp_dados['nome']
                            st.session_state.lgpd_aceito = False 
                            
                            st.query_params["logged_in"] = "true"
                            st.query_params["admin"] = "false"
                            st.query_params["empresa"] = emp_dados['nome']
                            registrar_auditoria("Acesso", "Login", f"Acessou o sistema de forma segura.", emp_dados['nome'])
                            st.rerun()
                        else:
                            st.error("Acesso Negado: Senha incorreta.")
                    else:
                        st.error("Acesso Negado: Login não encontrado.")
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(gerar_link_whatsapp("Tela de Login - Tentativa de acesso / Dúvida com Senha"), unsafe_allow_html=True)

# ==========================================
# 2. SISTEMA PRINCIPAL & MURO LGPD
# ==========================================
else:
    if not st.session_state.is_admin and not st.session_state.lgpd_aceito:
        res_lgpd = fetch_data("SELECT id FROM aceites_lgpd WHERE empresa=%s", (st.session_state.nome_empresa,))
        if res_lgpd:
            st.session_state.lgpd_aceito = True
            st.rerun()
        else:
            st.warning("⚠️ Adequação LGPD - Privacidade e Proteção de Dados")
            st.markdown("""
            ### TERMO DE RESPONSABILIDADE, CONFIDENCIALIDADE E ADEQUAÇÃO À LGPD
            
            A **AD Rastreamento Veicular**, sediada em São Gonçalo do Amarante, na qualidade de provedora do software de gestão e telemetria, estabelece as seguintes diretrizes obrigatórias para o uso da plataforma:
            
            **1. Sigilo e Confidencialidade:** O PARCEIRO compromete-se a manter absoluto sigilo sobre quaisquer dados pessoais de clientes (como Nomes, CPFs, Endereços, Placas e Posições de GPS) acessados através desta plataforma, utilizando-os única e exclusivamente para a prestação do serviço de rastreamento e monitoramento.
            
            **2. Responsabilidade Exclusiva:** O PARCEIRO declara ter ciência de que as credenciais de acesso ao sistema são de uso pessoal e intransferível. A responsabilidade por qualquer vazamento, cópia não autorizada, compartilhamento de telas ou uso indevido de dados de clientes a partir do seu painel recairá **exclusivamente sobre a empresa PARCEIRA**, isentando a AD Rastreamento Veicular de qualquer responsabilidade civil, administrativa ou penal.
            
            **3. Penalidades Legais:** O descumprimento das regras de proteção de dados sujeitará a empresa infratora ao bloqueio imediato do sistema, bem como à responsabilização por perdas e danos e às sanções previstas na Lei Geral de Proteção de Dados (Lei nº 13.709/2018).
            
            *Ao clicar em "Eu li e concordo", você assina digitalmente este termo, confirmando estar ciente e de acordo com suas responsabilidades jurídicas no trato dos dados hospedados na Central.*
            """)
            if st.button("✅ Eu li e concordo com os Termos e Políticas", type="primary"):
                agora_str = get_horario_brasil_str()
                assinatura_bruta = f"{st.session_state.nome_empresa}|{agora_str}|ADRASTREIO"
                hash_ass = hashlib.sha256(assinatura_bruta.encode('utf-8')).hexdigest()
                
                info_sessao = f"Navegador Web / Sessão Única: {st.session_state.session_uuid}"
                
                execute_query("INSERT INTO aceites_lgpd (empresa, data_hora, ip_aceite, hash_assinatura) VALUES (%s, %s, %s, %s)", 
                              (st.session_state.nome_empresa, agora_str, info_sessao, hash_ass))
                registrar_auditoria("Aceite LGPD", "Segurança", "Aceitou os termos de privacidade (Assinatura Eletrônica).", st.session_state.nome_empresa)
                st.session_state.lgpd_aceito = True
                st.rerun()
            st.stop()

    with st.sidebar:
        if not st.session_state.is_admin:
            logo_bytes = fetch_logo_cached(st.session_state.nome_empresa)
            if logo_bytes and len(logo_bytes) > 10:
                st.image(io.BytesIO(logo_bytes), width=140)

        st.write(f"👤 **Conectado como:** {st.session_state.nome_empresa}")
        
        if not st.session_state.is_admin:
            with st.expander("🖼️ Enviar / Alterar Minha Logo"):
                up_logo = st.file_uploader("Escolha a imagem (PNG/JPG)", type=["png", "jpg", "jpeg"], key="up_logo_parceiro")
                if up_logo is not None:
                    bytes_img = up_logo.getvalue()
                    conn = get_conn_fast()
                    cur = conn.cursor()
                    cur.execute("UPDATE empresas SET logo_binario = %s WHERE nome = %s", (bytes_img, st.session_state.nome_empresa))
                    conn.commit()
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
        alertas = fetch_data("SELECT * FROM notificacoes WHERE lida = FALSE ORDER BY id DESC")
        if alertas:
            st.markdown("### 🚨 Central de Alertas (Novos Cadastros)")
            for alerta in alertas:
                col_al1, col_al2 = st.columns([5, 1])
                col_al1.error(f"🔴 **NOVO VEÍCULO ADICIONADO ({alerta['empresa']}):** {alerta['mensagem']} - *{alerta['data_hora']}*")
                if col_al2.button("Limpar Aviso", key=f"limpar_notif_{alerta['id']}", use_container_width=True):
                    execute_query("UPDATE notificacoes SET lida = TRUE WHERE id = %s", (alerta['id'],))
                    st.rerun()
            st.markdown("---")

    if st.session_state.is_admin:
        res_count_pend = fetch_data("SELECT count(id) as c FROM historico WHERE tipo='Transferência' AND status='PENDENTE'")
    else:
        res_count_pend = fetch_data("SELECT count(id) as c FROM historico WHERE tipo='Transferência' AND status='PENDENTE' AND empresa=%s", (st.session_state.nome_empresa,))
    
    qtd_pend = res_count_pend[0]['c'] if res_count_pend else 0

    def formatar_nome_menu(aba_id):
        mapa = {
            "dashboard": "📊 Dashboard",
            "central": "🚨 Central 24h",
            "pendencias": f"🛠️ Pendências ({qtd_pend})",
            "clientes": "👤 Clientes",
            "relatorios": "📖 Relatórios",
            "empresas": "🏢 Empresas",
            "financeiro": "💰 Financeiro",
            "faturamento": "💰 Meu Faturamento",
            "cadastro": "⚙️ Meu Cadastro",
            "auditoria": "🕵️ Auditoria"
        }
        return mapa.get(aba_id, aba_id)

    if st.session_state.is_admin:
        lista_abas = ["dashboard", "central", "pendencias", "clientes", "relatorios", "empresas", "financeiro", "auditoria"]
    else:
        lista_abas = ["dashboard", "pendencias", "clientes", "relatorios", "faturamento", "cadastro", "auditoria"]
        
    aba_ativa = st.radio("Navegação", lista_abas, format_func=formatar_nome_menu, horizontal=True, label_visibility="collapsed")
    st.markdown("---")

    # =======================================================================
    # RENDERIZAÇÃO CONDICIONAL 
    # =======================================================================

    # --- TELA: DASHBOARD EXECUTIVO (INTELIGENTE E PROPORCIONAL) ---
    if aba_ativa == "dashboard":
        st.markdown("<h2 style='color: #4a0e4e; font-size: 24px; text-align: center;'>📊 Painel Executivo (Dashboard)</h2>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 14px; color: #666; text-align: center; margin-bottom: 30px;'>Visão executiva e laudos técnicos da operação de telemetria.</p>", unsafe_allow_html=True)
        
        if st.session_state.is_admin:
            empresas_disp_dash = fetch_data("SELECT nome FROM empresas ORDER BY nome")
            opcoes_emp_dash = ["Todas as Frotas (Visão Global)"] + [e['nome'] for e in empresas_disp_dash] if empresas_disp_dash else ["Todas as Frotas (Visão Global)"]
            
            col_filtro1, col_filtro2, col_filtro3 = st.columns([1, 2, 1])
            with col_filtro1:
                empresa_filtro_dash = st.selectbox("Filtrar por Empresa:", opcoes_emp_dash, key=f"dash_emp_{st.session_state.reset_keys['dash_mes']}")
            with col_filtro2:
                mes_atual = get_horario_brasil().strftime("%m/%Y")
                mes_filtro_dash = st.text_input("Filtrar Período de Análise (Mês/Ano):", value=mes_atual, key=f"dash_m_{st.session_state.reset_keys['dash_mes']}")
            
            if empresa_filtro_dash == "Todas as Frotas (Visão Global)":
                q_v = "SELECT v.tipo_veic FROM veiculos v JOIN clientes c ON v.cliente_id = c.id WHERE c.status = 'Ativo'"
                q_h = "SELECT tipo, detalhes FROM historico WHERE data_hora ILIKE %s"
                dados_v = fetch_data(q_v)
                dados_h = fetch_data(q_h, (f"%{mes_filtro_dash}%",))
                emp_alvo_rel = "Todas as Frotas (Visão Global)"
            else:
                q_v = "SELECT v.tipo_veic FROM veiculos v JOIN clientes c ON v.cliente_id = c.id WHERE c.empresa = %s AND c.status = 'Ativo'"
                q_h = "SELECT tipo, detalhes FROM historico WHERE empresa=%s AND data_hora ILIKE %s"
                dados_v = fetch_data(q_v, (empresa_filtro_dash,))
                dados_h = fetch_data(q_h, (empresa_filtro_dash, f"%{mes_filtro_dash}%"))
                emp_alvo_rel = empresa_filtro_dash
        else:
            col_filtro1, col_filtro2, col_filtro3 = st.columns([1, 2, 1])
            with col_filtro2:
                mes_atual = get_horario_brasil().strftime("%m/%Y")
                mes_filtro_dash = st.text_input("Filtrar Período de Análise (Mês/Ano):", value=mes_atual, key=f"dash_m_{st.session_state.reset_keys['dash_mes']}")
            
            q_v = "SELECT v.tipo_veic FROM veiculos v JOIN clientes c ON v.cliente_id = c.id WHERE c.empresa = %s AND c.status = 'Ativo'"
            q_h = "SELECT tipo, detalhes FROM historico WHERE empresa=%s AND data_hora ILIKE %s"
            dados_v = fetch_data(q_v, (st.session_state.nome_empresa,))
            dados_h = fetch_data(q_h, (st.session_state.nome_empresa, f"%{mes_filtro_dash}%"))
            emp_alvo_rel = st.session_state.nome_empresa

        df_frota = pd.DataFrame(dados_v) if dados_v else pd.DataFrame(columns=['tipo_veic'])
        
        eventos_parse = []
        if dados_h:
            for row in dados_h:
                if row['tipo'] in ['Furto', 'Roubo']:
                    eventos_parse.append(row['tipo'])
                else:
                    detalhe = str(row.get('detalhes', ''))
                    if "Evento: " in detalhe:
                        evt_extraido = detalhe.split("Evento: ")[1].split(" |")[0]
                        eventos_parse.append(evt_extraido)
                    else:
                        eventos_parse.append(row['tipo'])
        
        df_eventos = pd.DataFrame(eventos_parse, columns=['Evento'])
        
        col_graf1, col_graf2 = st.columns(2)
        
        with col_graf1:
            st.markdown("<div class='dash-title'>🚗 Composição da Frota</div>", unsafe_allow_html=True)
            if not df_frota.empty:
                contagem_frota = df_frota['tipo_veic'].value_counts().reset_index()
                contagem_frota.columns = ['Categoria', 'Quantidade']
                
                grafico_frota = alt.Chart(contagem_frota).mark_arc(innerRadius=60).encode(
                    theta=alt.Theta(field="Quantidade", type="quantitative"),
                    color=alt.Color(field="Categoria", type="nominal", scale=alt.Scale(range=['#4a0e4e', '#8b0000', '#6a1b9a', '#b71c1c'])),
                    tooltip=["Categoria", "Quantidade"]
                ).properties(height=280)
                
                st.altair_chart(grafico_frota, use_container_width=True)
                
                st.markdown("<div style='margin-top: 10px;'>", unsafe_allow_html=True)
                for _, row in contagem_frota.iterrows():
                    st.markdown(f"<div class='dash-legend'><span><b>{row['Categoria']}</b></span> <span>{row['Quantidade']} unidade(s)</span></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("Nenhum veículo cadastrado na frota ativa.")

        with col_graf2:
            st.markdown("<div class='dash-title'>🛠️ Incidência de Atendimentos</div>", unsafe_allow_html=True)
            if not df_eventos.empty:
                contagem_eventos = df_eventos['Evento'].value_counts().reset_index()
                contagem_eventos.columns = ['Ocorrência', 'Total']
                
                grafico_eventos = alt.Chart(contagem_eventos).mark_arc(innerRadius=60).encode(
                    theta=alt.Theta(field="Total", type="quantitative"),
                    color=alt.Color(field="Ocorrência", type="nominal", scale=alt.Scale(scheme="purples")),
                    tooltip=["Ocorrência", "Total"]
                ).properties(height=280)
                
                st.altair_chart(grafico_eventos, use_container_width=True)
                
                st.markdown("<div style='margin-top: 10px;'>", unsafe_allow_html=True)
                for _, row in contagem_eventos.iterrows():
                    st.markdown(f"<div class='dash-legend'><span><b>{row['Ocorrência']}</b></span> <span>{row['Total']} chamado(s)</span></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("Nenhum evento operacional registrado para este período.")

        # --- A CEREJA DO BOLO: LAUDO DIAGNÓSTICO INTELIGENTE (COM BOTÃO ABRIR/FECHAR) ---
        st.markdown("<br><hr>", unsafe_allow_html=True)
        st.markdown("<h3 style='color: #4a0e4e; font-size: 20px; text-align: center;'>📄 Sistema de Inteligência Operacional</h3>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 13px; color: #666; text-align: center;'>Gere um laudo automático baseado no maior gargalo técnico que a frota enfrentou neste mês.</p>", unsafe_allow_html=True)
        
        col_laudo1, col_laudo2, col_laudo3 = st.columns([1, 2, 1])
        with col_laudo2:
            if not st.session_state.mostrar_laudo:
                if st.button("🚀 Processar Laudo Executivo do Mês", type="primary", use_container_width=True):
                    if df_eventos.empty:
                        st.warning("Não há chamados suficientes para gerar um laudo analítico neste mês.")
                    else:
                        st.session_state.mostrar_laudo = True
                        st.rerun()
                        
            if st.session_state.mostrar_laudo:
                # Recalcula caso a tela tenha sido apenas recarregada
                contagem_eventos = df_eventos['Evento'].value_counts().reset_index()
                contagem_eventos.columns = ['Ocorrência', 'Total']
                
                evento_campeao = contagem_eventos.iloc[0]['Ocorrência']
                total_campeao = contagem_eventos.iloc[0]['Total']
                total_geral_chamados = df_eventos.shape[0]
                porcentagem_campeao = (total_campeao / total_geral_chamados) * 100
                
                detalhamento_operacional = ""
                for _, row in contagem_eventos.iterrows():
                    evt = row['Ocorrência']
                    qtd = row['Total']
                    pct = (qtd / total_geral_chamados) * 100
                    detalhamento_operacional += f"   • {evt}: {qtd} chamado(s) ({pct:.1f}%)\n"
                
                dict_diag = DIAGNOSTICOS_TECNICOS.get(evento_campeao, {
                    "diagnostico": f"Identificamos um número atípico do evento '{evento_campeao}'.",
                    "causa": "Pode ter sido ocasionado por instabilidades pontuais no sistema, variações elétricas no veículo ou uso inadequado.",
                    "acao": "Manter os veículos em observação e orientar a base de motoristas sobre as regras de uso padrão."
                })
                
                texto_laudo_markdown = f"""
======================================================
LAUDO DE DESEMPENHO OPERACIONAL - {mes_filtro_dash}
======================================================

EMPRESA / FROTA: {emp_alvo_rel}
TOTAL DE CHAMADOS NO MÊS: {total_geral_chamados}

-- DETALHAMENTO OPERACIONAL (DISTRIBUIÇÃO DE EVENTOS) --
{detalhamento_operacional}

O sistema de inteligência técnica analisou a telemetria do período e identificou que o gargalo operacional principal da sua frota foi focado em:

>> ALERTA PRINCIPAL: {evento_campeao}
Este evento representou {porcentagem_campeao:.1f}% de todo o fluxo operacional da central ({total_campeao} chamados de um total de {total_geral_chamados}).

-- DIAGNÓSTICO TÉCNICO ({evento_campeao}) --
{dict_diag['diagnostico']}

-- CAUSA RAIZ PROVÁVEL --
{dict_diag['causa']}

-- PLANO DE AÇÃO E SUGESTÃO DA CENTRAL --
{dict_diag['acao']}

======================================================
Gerado pelo Sistema Oficial AD Rastreamento Veicular
                """
                
                st.success("Laudo analisado e gerado com sucesso!")
                st.markdown(f"""
                <div style="background-color: #f0f4f8; padding: 20px; border-left: 5px solid #8b0000; border-radius: 5px; font-family: monospace; white-space: pre-wrap; font-size: 13px; line-height: 1.5; color: #333; margin-bottom: 15px;">{texto_laudo_markdown}</div>
                """, unsafe_allow_html=True)
                
                col_btn_laudo1, col_btn_laudo2 = st.columns(2)
                with col_btn_laudo1:
                    st.download_button(
                        label="📥 Baixar Laudo de Texto",
                        data=texto_laudo_markdown,
                        file_name=f"Laudo_Tecnico_{emp_alvo_rel.replace(' ', '_')}_{mes_filtro_dash.replace('/', '_')}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                with col_btn_laudo2:
                    if st.button("❌ Fechar Laudo", use_container_width=True):
                        st.session_state.mostrar_laudo = False
                        st.rerun()

    # --- TELA: OPERAÇÃO 24H (SÓ ADMIN) ---
    elif aba_ativa == "central" and st.session_state.is_admin:
        st.header("🚨 Central de Operações e Ocorrências 24h")
        
        if st.session_state.get('link_transferencia'):
            st.success("✅ Ficha de transferência salva como pendência e pronta para ser enviada!")
            
            link_wpp = st.session_state.link_transferencia
            emp = st.session_state.empresa_transferencia
            
            st.markdown(f'<a href="{link_wpp}" target="_blank" style="text-decoration:none;"><button style="background-color:#25D366; color:white; padding:15px; border-radius:5px; border:none; font-weight:bold; cursor:pointer; width:100%; font-size:16px;">💬 Clicar Aqui para Enviar a Solicitação no WhatsApp da {emp}</button></a>', unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.button("🧹 Limpar Tela e Iniciar Novo Atendimento", type="primary", use_container_width=True):
                limpar_tela()
                st.rerun()
        else:
            col_b1, col_b2 = st.columns([4, 1])
            busca_op_input = col_b1.text_input("🔍 Busca Inteligente (Nome, Placa ou CPF):", key=f"busca_op_{st.session_state.rk}")
            btn_buscar = col_b2.button("Pesquisar Veículo", use_container_width=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            if btn_buscar and len(busca_op_input) >= 3:
                st.session_state.termo_busca_ativo = busca_op_input
            elif busca_op_input != st.session_state.get("termo_busca_ativo", ""):
                st.session_state.termo_busca_ativo = ""
                
            if st.session_state.termo_busca_ativo:
                termo = f"%{st.session_state.termo_busca_ativo}%"
                q_busca = """
                    SELECT c.nome, c.documento, c.telefone, c.empresa, v.placa, v.modelo, v.cor, v.tipo_veic 
                    FROM clientes c JOIN veiculos v ON c.id = v.cliente_id 
                    WHERE c.status='Ativo' AND (c.nome ILIKE %s OR v.placa ILIKE %s OR c.documento ILIKE %s)
                """
                resultados = fetch_data(q_busca, (termo, termo, termo))
                
                if resultados:
                    st.success("Veículos encontrados! Selecione abaixo para iniciar a ocorrência.")
                    
                    placas_disponiveis = [f"{r['placa']} - {r['nome']} ({r['modelo']}) - {r['empresa']}" for r in resultados]
                    placa_sel_texto = st.selectbox("Selecione o Veículo para Atendimento:", placas_disponiveis, key=f"sel_veic_{st.session_state.rk}")
                    
                    if placa_sel_texto:
                        placa_sel = placa_sel_texto.split(" - ")[0]
                        info_veic = next(item for item in resultados if item["placa"] == placa_sel)
                        
                        st.markdown("---")
                        tipo_servico = st.radio("📋 **Ação na Central:**", ["Abertura de Furto/Roubo", "Monitoramento Técnico"], horizontal=True, key=f"radio_serv_{st.session_state.rk}")
                        
                        if tipo_servico == "Abertura de Furto/Roubo":
                            st.markdown("<h3 style='color: #8b0000;'>Abertura de Furto/Roubo (Início Automático)</h3>", unsafe_allow_html=True)
                            
                            col_oc1, col_oc2 = st.columns(2)
                            tipo_oc = col_oc1.selectbox("Natureza", ["Furto", "Roubo"], key=f"nat_{st.session_state.rk}")
                            local_oc = col_oc2.text_input("Localização do Fato", key=f"loc_{st.session_state.rk}")
                            
                            col_chip1, col_chip2 = st.columns(2)
                            status_chip = col_chip1.text_input("📡 Última Posição / Status do Chip", key=f"chip_{st.session_state.rk}")
                            link_rastreio = col_chip2.text_input("🔗 Link de Rastreio (Para Polícia/Cliente)", key=f"link_{st.session_state.rk}")
                            
                            desc_oc = st.text_area("Descrição / Dinâmica", key=f"desc_{st.session_state.rk}")
                            st.markdown("<p style='font-size: 13px; color: #555;'>ℹ️ Status inicial configurado automaticamente como: EM ANDAMENTO. O cronômetro de resposta foi iniciado.</p>", unsafe_allow_html=True)
                            
                            if st.button("🚨 Salvar Ocorrência", type="primary"):
                                agora = get_horario_brasil_str()
                                detalhes_completos = f"Local: {local_oc} | Desc: {desc_oc} | Chip/Posição: {status_chip} | Link Rastreio: {link_rastreio}"
                                execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (%s,%s,%s,%s,%s,%s,%s)", 
                                              (agora, info_veic['nome'], placa_sel, tipo_oc, "EM ANDAMENTO", detalhes_completos, info_veic['empresa']))
                                registrar_auditoria("Registro", "Operação", f"Ocorrência de {tipo_oc} INICIADA para {placa_sel}", info_veic['empresa'])
                                st.session_state.flash_msg = "Salvo e enviado para relatórios como EM ANDAMENTO!"
                                limpar_tela()
                                st.rerun()
                        
                        elif tipo_servico == "Monitoramento Técnico":
                            st.markdown("<h3 style='color: #4a0e4e;'>Monitoramento Técnico / Transferência</h3>", unsafe_allow_html=True)
                            col_m1, col_m2 = st.columns(2)
                            
                            lista_eventos = [
                                "Cerca Virtual", 
                                "Desconexão de Bateria", 
                                "Falta de Comunicação", 
                                "Transferência - Setor Financeiro", 
                                "Transferência - Setor Técnico", 
                                "Outros"
                            ]
                            
                            evento_mon = col_m1.selectbox("Evento", lista_eventos, key=f"eve_{st.session_state.rk}")
                            status_chip = col_m2.text_input("📡 Status do Rastreador / Chip", key=f"chip_m_{st.session_state.rk}")
                            
                            acao_mon = st.text_area("Ação da Central / Detalhes da Solicitação", key=f"aca_{st.session_state.rk}")
                            
                            eh_transferencia = "Transferência" in evento_mon
                            
                            if eh_transferencia:
                                st.info(f"💡 **Roteamento e Abertura de Ticket:** Essa solicitação irá para a aba **Pendências** e o link do WhatsApp para a **{info_veic['empresa']}** será gerado em seguida.")
                            
                            texto_botao = "📲 Abrir Pendência e Gerar WhatsApp" if eh_transferencia else "💾 Salvar Monitoramento"
                            
                            if st.button(texto_botao, type="primary"):
                                agora = get_horario_brasil_str()
                                detalhes_completos = f"Evento: {evento_mon} | Status Equipamento: {status_chip} | Ação/Motivo: {acao_mon}"
                                
                                tipo_hist = "Transferência" if eh_transferencia else "Monitoramento"
                                status_hist = "PENDENTE" if eh_transferencia else "FINALIZADO"
                                
                                execute_query("INSERT INTO historico (data_hora, cliente, placa, tipo, status, detalhes, empresa) VALUES (%s,%s,%s,%s,%s,%s,%s)", 
                                              (agora, info_veic['nome'], placa_sel, tipo_hist, status_hist, detalhes_completos, info_veic['empresa']))
                                
                                texto_audit = f"Chamado aberto para {placa_sel}" if eh_transferencia else f"Evento para {placa_sel}"
                                registrar_auditoria("Registro", tipo_hist, texto_audit, info_veic['empresa'])
                                
                                if eh_transferencia:
                                    res_empresa = fetch_data("SELECT telefone FROM empresas WHERE nome=%s", (info_veic['empresa'],))
                                    tel_bruto = res_empresa[0]['telefone'] if res_empresa and res_empresa[0]['telefone'] else ""
                                    
                                    tel_limpo = re.sub(r'\D', '', str(tel_bruto))
                                    
                                    if tel_limpo:
                                        if not tel_limpo.startswith('55'):
                                            tel_limpo = f"55{tel_limpo}"
                                            
                                        setor_nome = "FINANCEIRO (Faturas/Cobranças)" if "Financeiro" in evento_mon else "TÉCNICO (Manutenção/Offline)"
                                        msg_wpp = f"🚨 *NOVO CHAMADO PENDENTE - SETOR {setor_nome}* 🚨\n\n"
                                        msg_wpp += f"🏢 *Base Parceira:* {info_veic['empresa']}\n"
                                        msg_wpp += f"👤 *Cliente:* {info_veic['nome']}\n"
                                        msg_wpp += f"🚗 *Veículo:* {placa_sel} ({info_veic['modelo']})\n"
                                        msg_wpp += f"📝 *Solicitação/Motivo:* {acao_mon}\n\n"
                                        msg_wpp += f"Este chamado já se encontra aberto na aba PENDÊNCIAS do sistema. Favor assumir, aplicar a resolução e finalizar o chamado por lá."
                                        
                                        msg_codificada = urllib.parse.quote(msg_wpp)
                                        link_wpp = f"https://wa.me/{tel_limpo}?text={msg_codificada}"
                                        
                                        st.session_state.link_transferencia = link_wpp
                                        st.session_state.empresa_transferencia = info_veic["empresa"]
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Falha no roteamento: A empresa **{info_veic['empresa']}** não possui um telefone válido cadastrado. Vá na aba Empresas e atualize o cadastro.")
                                else:
                                    st.session_state.flash_msg = "Salvo com sucesso!"
                                    limpar_tela()
                                    st.rerun()
                    else:
                        st.warning("Nenhum veículo encontrado com este termo.")

    # --- TELA: GESTÃO DE PENDÊNCIAS ---
    elif aba_ativa == "pendencias":
        st.header("🛠️ Gestão de Chamados e Pendências")
        st.markdown("<p style='font-size: 13px; color: #666;'>Painel de transferências financeiras e técnicas aguardando resolução pela empresa parceira. Finalizar um chamado encerra o documento e o transfere para os Relatórios.</p>", unsafe_allow_html=True)
        
        q_pend = "SELECT * FROM historico WHERE tipo='Transferência' AND status='PENDENTE' ORDER BY id DESC"
        if not st.session_state.is_admin:
            q_pend = "SELECT * FROM historico WHERE tipo='Transferência' AND status='PENDENTE' AND empresa=%s ORDER BY id DESC"
            res_pend = fetch_data(q_pend, (st.session_state.nome_empresa,))
        else:
            res_pend = fetch_data(q_pend)
            
        if res_pend:
            for p in res_pend:
                with st.expander(f"🔴 CHAMADO PENDENTE #{p['id']} - {p['cliente']} (Placa: {p['placa']}) - {p['data_hora']}", expanded=False):
                    st.write(f"**Empresa Responsável:** {p['empresa']}")
                    st.write(f"**Detalhes da Solicitação Inicial:**")
                    st.info(p['detalhes'])
                    
                    st.markdown("---")
                    st.write("🟢 **Finalizar Chamado (Resolver Pendência):**")
                    desfecho_pend = st.text_area("Descreva o desfecho ou a solução aplicada (Ex: 'Fatura regularizada' ou 'Equipamento resetado e online'):", key=f"desf_pend_{p['id']}")
                    
                    if st.button("✅ Marcar como Resolvido / Encerrar Documento", key=f"btn_res_pend_{p['id']}", type="primary"):
                        if not desfecho_pend.strip():
                            st.error("Por favor, preencha o desfecho antes de finalizar o chamado.")
                        else:
                            agora = get_horario_brasil_str()
                            novo_detalhe = f"{p['detalhes']} | RESOLUÇÃO ({agora}): {desfecho_pend}"
                            execute_query("UPDATE historico SET status='FINALIZADO', detalhes=%s WHERE id=%s", (novo_detalhe, p['id']))
                            
                            registrar_auditoria("Resolução", "Pendências", f"Chamado #{p['id']} ({p['placa']}) finalizado. Desfecho: {desfecho_pend}", p['empresa'])
                            st.session_state.flash_msg = f"Chamado #{p['id']} resolvido com sucesso! O registro e as assinaturas foram fechados nos Relatórios."
                            st.rerun()
        else:
            st.success("✅ Nenhuma pendência em aberto no momento. Todos os chamados financeiros e técnicos foram resolvidos e finalizados!")

    # --- TELA: CLIENTES E FROTAS ---
    elif aba_ativa == "clientes":
        st.header("👤 Gerenciamento de Clientes e Frotas Multi-Veículos")
        
        opcoes_acao = ["Listar", "Incluir Novo", "Importação em Lote", "Editar"]
        if st.session_state.is_admin:
            opcoes_acao.append("Excluir")
        else:
            opcoes_acao.append("Solicitar Exclusão")

        acao_clientes = st.radio("Ação Clientes:", opcoes_acao, horizontal=True)
        st.markdown("---")
        
        empresas_disp = fetch_data("SELECT nome FROM empresas ORDER BY nome")
        opcoes_emp = [e['nome'] for e in empresas_disp] if st.session_state.is_admin else [st.session_state.nome_empresa]

        if acao_clientes == "Listar":
            busca_cli = st.text_input("🔍 Busca Inteligente (Nome, Placa ou CPF):", key=f"lista_busca_{st.session_state.rk}")
            
            q_tela = """
                SELECT c.id as cli_id, c.nome, c.documento, c.telefone, c.empresa, c.status, c.endereco,
                       (SELECT COUNT(v.id) FROM veiculos v WHERE v.cliente_id = c.id) as qtd_veiculos
                FROM clientes c 
                WHERE 1=1
            """
            params_tela = []
            if not st.session_state.is_admin:
                q_tela += " AND c.empresa = %s"
                params_tela.append(st.session_state.nome_empresa)
                
            if busca_cli and len(busca_cli) >= 3:
                termo = f"%{busca_cli}%"
                q_tela += " AND (c.nome ILIKE %s OR c.documento ILIKE %s OR EXISTS (SELECT 1 FROM veiculos v2 WHERE v2.cliente_id = c.id AND v2.placa ILIKE %s))"
                params_tela.extend([termo, termo, termo])
                
            q_tela += " ORDER BY c.empresa, c.nome"
            
            res_tela = fetch_data(q_tela, tuple(params_tela))
            
            if res_tela:
                df_tela = pd.DataFrame(res_tela)
                empresas_ativas = df_tela['empresa'].unique()
                
                for emp_ativa in empresas_ativas:
                    with st.expander(f"📁 Clientes da Empresa: {emp_ativa}"):
                        df_emp = df_tela[df_tela['empresa'] == emp_ativa]
                        df_display = df_emp[['nome', 'documento', 'telefone', 'qtd_veiculos', 'status']].copy()
                        df_display.columns = ['Cliente', 'CPF/CNPJ', 'Telefone', 'Qtd. Veículos', 'Status']
                        st.dataframe(df_display, use_container_width=True)
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        lista_ficha_op = [""] + [f"{row['cli_id']} - {row['nome']} (CPF/CNPJ: {row['documento']})" for _, row in df_emp.iterrows()]
                        k_ficha_cli = st.session_state.reset_keys.get('ficha_cli', 0)
                        
                        cli_ficha_sel = st.selectbox(f"🔍 Selecione um cliente da {emp_ativa} para ver a Ficha Completa:", lista_ficha_op, key=f"sb_ficha_cli_{emp_ativa}_{k_ficha_cli}")
                        
                        if cli_ficha_sel != "":
                            id_cli_ficha = int(cli_ficha_sel.split(" - ")[0])
                            dados_cli_ficha = fetch_data("SELECT * FROM clientes WHERE id=%s", (id_cli_ficha,))[0]
                            veiculos_cli_ficha = fetch_data("SELECT * FROM veiculos WHERE cliente_id=%s", (id_cli_ficha,))
                            
                            if st.session_state.last_viewed_cli != id_cli_ficha:
                                registrar_auditoria("Visualização", "Clientes", f"Visualizou a ficha completa do cliente: {dados_cli_ficha['nome']}", dados_cli_ficha['empresa'])
                                st.session_state.last_viewed_cli = id_cli_ficha
                            
                            if st.button("❌ Fechar Ficha Cadastral", key=f"btn_close_ficha_cli_{id_cli_ficha}_{emp_ativa}"):
                                limpar_tela()
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
                                df_veics = pd.DataFrame(veiculos_cli_ficha)[['tipo_veic', 'placa', 'modelo', 'cor', 'info_chip']]
                                df_veics.columns = ['Tipo', 'Placa', 'Modelo', 'Cor', 'Chip/Equipamento']
                                st.dataframe(df_veics, use_container_width=True)
                            else:
                                st.info("Nenhum veículo vinculado a este cliente.")
                                
                            st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("Nenhum cliente encontrado para esta busca.")
                
        elif acao_clientes == "Incluir Novo":
            if not opcoes_emp:
                st.error("Nenhuma empresa parceira cadastrada! Cadastre a empresa primeiro.")
            else:
                st.subheader("📝 Cadastro de Novo Cliente e Seus Veículos")
                
                rk = st.session_state.rk
                
                st.markdown("<div class='ficha-box'>", unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                f_nome = c1.text_input("Nome do Cliente *", key=f"in_nome_{rk}")
                f_doc = c2.text_input("CPF / CNPJ *", key=f"in_doc_{rk}")
                f_end = c1.text_input("Endereço", key=f"in_end_{rk}")
                f_tel = c2.text_input("Telefone", key=f"in_tel_{rk}")
                f_emp = c1.selectbox("Empresa (Pasta) *", opcoes_emp, key=f"in_emp_{rk}")
                
                st.markdown("---")
                st.write("🚗 **Frota / Veículos do Cliente:**")
                
                col_b1, col_b2 = st.columns([1, 4])
                with col_b1:
                    if st.button("➕ Adicionar Veículo", type="secondary"):
                        st.session_state.num_veiculos_state += 1
                        st.rerun()
                with col_b2:
                    if st.session_state.num_veiculos_state > 1:
                        if st.button("➖ Remover Último Veículo", type="secondary"):
                            st.session_state.num_veiculos_state -= 1
                            st.rerun()

                veiculos_dados = []
                for i in range(st.session_state.num_veiculos_state):
                    st.markdown(f"**Veículo {i+1}**")
                    vc1, vc2, vc3, vc4, vc5 = st.columns([2, 2, 2, 2, 3])
                    t_veic = vc1.selectbox(f"Tipo {i+1}", ["Carro", "Moto", "Caminhão", "Outro"], key=f"in_t_{i}_{rk}")
                    p_veic = vc2.text_input(f"Placa * {i+1}", key=f"in_p_{i}_{rk}")
                    m_veic = vc3.text_input(f"Modelo {i+1}", key=f"in_m_{i}_{rk}")
                    c_veic = vc4.text_input(f"Cor {i+1}", key=f"in_c_{i}_{rk}")
                    chip_veic = vc5.text_input(f"Chip/Equipamento (Opcional)", key=f"in_chip_{i}_{rk}")
                    
                    veiculos_dados.append({"tipo": t_veic, "placa": p_veic, "modelo": m_veic, "cor": c_veic, "info_chip": chip_veic})
                    st.markdown("---")

                if st.button("💾 Salvar Cadastro Completo", type="primary"):
                    if f_nome and f_doc and any(v['placa'].strip() for v in veiculos_dados):
                        conn = get_conn_fast()
                        cur = conn.cursor(cursor_factory=RealDictCursor)
                        cur.execute("INSERT INTO clientes (nome, documento, endereco, telefone, empresa, status) VALUES (%s,%s,%s,%s,%s,'Ativo') RETURNING id", 
                                       (f_nome, f_doc, f_end, f_tel, f_emp))
                        cliente_id = cur.fetchone()['id']
                        
                        validos = [v for v in veiculos_dados if v['placa'].strip()]
                        for v in validos:
                            cur.execute("INSERT INTO veiculos (cliente_id, tipo_veic, placa, modelo, cor, info_chip) VALUES (%s,%s,%s,%s,%s,%s)", 
                                           (cliente_id, v['tipo'], v['placa'], v['modelo'], v['cor'], v['info_chip']))
                        conn.commit()
                        st.cache_data.clear()
                        
                        total_cad = len(validos)
                        msg_veic = f"1 veículo" if total_cad == 1 else f"{total_cad} veículos"

                        registrar_auditoria("Cadastro", "Clientes", f"Cliente {f_nome} cadastrado com {msg_veic}.", f_emp)
                        
                        agora_notif = get_horario_brasil_str()
                        execute_query("INSERT INTO notificacoes (data_hora, empresa, mensagem) VALUES (%s, %s, %s)", 
                                      (agora_notif, f_emp, f"Novo cliente '{f_nome}' cadastrado com {msg_veic}."))

                        st.session_state.flash_msg = "Cliente e veículos cadastrados com sucesso!"
                        st.session_state.num_veiculos_state = 1
                        limpar_tela()
                        st.rerun()
                    else:
                        st.error("Preencha o Nome, CPF/CNPJ e pelo menos a Placa de um veículo.")
                st.markdown("</div>", unsafe_allow_html=True)
                            
        elif acao_clientes == "Importação em Lote":
            st.subheader("📥 Importação Inteligente via CSV")
            st.markdown("<p style='font-size: 13px; color: #666;'>O sistema agrupará todos os veículos vinculados ao mesmo documento automaticamente.</p>", unsafe_allow_html=True)
            
            emp_lote = st.selectbox("Selecione a Empresa de destino para a importação:", opcoes_emp, key=f"emp_lote_sel_{st.session_state.rk}")
            
            df_exemplo = pd.DataFrame({
                "Nome": ["João da Silva", "João da Silva"],
                "CPF / CNPJ": ["123.456.789-00", "123.456.789-00"],
                "Endereço": ["Rua A, 100", "Rua A, 100"],
                "Telefone": ["(84) 99999-1111", "(84) 99999-1111"],
                "Tipo": ["Carro", "Moto"],
                "Placa": ["ABC-1234", "XYZ-5678"],
                "Modelo": ["Fiat Palio", "Honda CG"],
                "Cor": ["Prata", "Vermelha"]
            })
            st.download_button(label="📄 Baixar Planilha Modelo (CSV)", data=df_exemplo.to_csv(index=False).encode('utf-8'), file_name="Modelo_Importacao_Frotas.csv", mime="text/csv")
            
            arquivo_csv = st.file_uploader("Escolha a sua planilha CSV preenchida", type=["csv"], key=f"up_csv_{st.session_state.rk}")
            if arquivo_csv is not None:
                try:
                    df_import = pd.read_csv(arquivo_csv).fillna("")
                    if st.button("🚀 Processar Importação Inteligente"):
                        importados_clientes = 0
                        importados_veiculos = 0
                        
                        col_doc = "CPF / CNPJ" if "CPF / CNPJ" in df_import.columns else ("Documento" if "Documento" in df_import.columns else None)
                        if not col_doc:
                            st.error("ERRO: A coluna 'CPF / CNPJ' não foi encontrada na sua planilha. Por favor, baixe o modelo acima.")
                            st.stop()

                        conn = get_conn_fast()
                        cur = conn.cursor(cursor_factory=RealDictCursor)

                        for doc, group in df_import.groupby(col_doc):
                            doc_str = str(doc).strip()
                            if not doc_str: continue
                            
                            primeira_linha = group.iloc[0]
                            nome = str(primeira_linha.get("Nome", "")).strip()
                            end = str(primeira_linha.get("Endereço", "")).strip()
                            tel = str(primeira_linha.get("Telefone", "")).strip()
                            
                            if not nome: continue

                            cur.execute("SELECT id FROM clientes WHERE documento=%s AND empresa=%s", (doc_str, emp_lote))
                            cli_res = cur.fetchone()
                            
                            if cli_res:
                                cli_id = cli_res['id']
                            else:
                                cur.execute("INSERT INTO clientes (nome, documento, endereco, telefone, empresa, status) VALUES (%s,%s,%s,%s,%s,'Ativo') RETURNING id", 
                                            (nome, doc_str, end, tel, emp_lote))
                                cli_id = cur.fetchone()['id']
                                importados_clientes += 1
                                
                            for _, row in group.iterrows():
                                tipo = str(row.get("Tipo", "Carro")).strip()
                                placa = str(row.get("Placa", "")).strip()
                                modelo = str(row.get("Modelo", "")).strip()
                                cor = str(row.get("Cor", "")).strip()
                                
                                if placa:
                                    cur.execute("INSERT INTO veiculos (cliente_id, tipo_veic, placa, modelo, cor) VALUES (%s,%s,%s,%s,%s)", 
                                                (cli_id, tipo, placa, modelo, cor))
                                    importados_veiculos += 1

                        conn.commit()
                        st.cache_data.clear()        
                        registrar_auditoria("Importação Lote", "Clientes", f"Importação CSV: {importados_clientes} clientes e {importados_veiculos} veículos.", emp_lote)
                        
                        agora_notif = get_horario_brasil_str()
                        execute_query("INSERT INTO notificacoes (data_hora, empresa, mensagem) VALUES (%s, %s, %s)", 
                                      (agora_notif, emp_lote, f"Importação via planilha concluída: {importados_clientes} cliente(s) e {importados_veiculos} veículo(s)."))

                        st.session_state.flash_msg = f"Sucesso! {importados_clientes} clientes agrupados/criados e {importados_veiculos} veículos inseridos."
                        limpar_tela()
                        st.rerun()
                except Exception as e:
                    st.error(f"Erro ao processar CSV: {e}")
            
        elif acao_clientes in ["Editar", "Excluir"]:
            col_pesq1, col_pesq2 = st.columns([4, 1])
            busca = col_pesq1.text_input("🔍 Busca Inteligente (Nome, Placa ou CPF):", key=f"edit_busca_{st.session_state.rk}")
            btn_pesq = col_pesq2.button("Pesquisar Cliente", type="primary", use_container_width=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            if btn_pesq and busca and len(busca) >= 3:
                st.session_state.termo_cli_ativo = busca
                
            if st.session_state.termo_cli_ativo:
                termo_c = f"%{st.session_state.termo_cli_ativo}%"
                
                q_cli_busca = """
                    SELECT DISTINCT c.id, c.nome, c.documento FROM clientes c 
                    WHERE (c.nome ILIKE %s OR c.documento ILIKE %s OR EXISTS (SELECT 1 FROM veiculos v WHERE v.cliente_id = c.id AND v.placa ILIKE %s))
                """
                params_busca = [termo_c, termo_c, termo_c]

                if not st.session_state.is_admin:
                    q_cli_busca += " AND c.empresa = %s"
                    params_busca.append(st.session_state.nome_empresa)
                
                res_cli_busca = fetch_data(q_cli_busca, tuple(params_busca))
                
                if res_cli_busca:
                    opcoes_cli = [f"{item['id']} - {item['nome']} (CPF/CNPJ: {item['documento']})" for item in res_cli_busca]
                    k_edit_cli = st.session_state.reset_keys['edit_cli']
                    
                    if acao_clientes == "Editar":
                        cli_escolhido = st.selectbox("Selecione o Cliente para Editar:", [""] + opcoes_cli, key=f"sb_edit_cli_{k_edit_cli}")
                        
                        if cli_escolhido != "":
                            id_c_sel = int(cli_escolhido.split(" - ")[0])
                            dados_cliente_sel = fetch_data("SELECT * FROM clientes WHERE id=%s", (id_c_sel,))[0]
                            veiculos_cliente = fetch_data("SELECT * FROM veiculos WHERE cliente_id=%s", (id_c_sel,))
                            
                            st.markdown("---")
                            st.write("📝 **Atualizando Dados Cadastrais:**")
                            en_nome = st.text_input("Nome", value=dados_cliente_sel['nome'], key=f"e_nome_{id_c_sel}")
                            en_doc = st.text_input("CPF/CNPJ", value=dados_cliente_sel['documento'], key=f"e_doc_{id_c_sel}")
                            en_end = st.text_input("Endereço", value=dados_cliente_sel.get('endereco', ''), key=f"e_end_{id_c_sel}")
                            en_tel = st.text_input("Telefone", value=dados_cliente_sel['telefone'], key=f"e_tel_{id_c_sel}")
                            
                            st.markdown("---")
                            st.write("🚗 **Veículos Já Vinculados (Edite os dados abaixo):**")
                            veiculos_editados = []
                            if veiculos_cliente:
                                for idx, v in enumerate(veiculos_cliente):
                                    st.write(f"**Veículo {idx+1} (Placa Atual: {v['placa']})**")
                                    vc1, vc2, vc3, vc4, vc5 = st.columns([2, 2, 2, 2, 3])
                                    tipos_v = ["Carro", "Moto", "Caminhão", "Outro"]
                                    t_idx = tipos_v.index(v['tipo_veic']) if v['tipo_veic'] in tipos_v else 0
                                    
                                    e_tipo = vc1.selectbox(f"Tipo", tipos_v, index=t_idx, key=f"e_t_{v['id']}")
                                    e_placa = vc2.text_input(f"Placa", value=v['placa'], key=f"e_p_{v['id']}")
                                    e_modelo = vc3.text_input(f"Modelo", value=v['modelo'], key=f"e_m_{v['id']}")
                                    e_cor = vc4.text_input(f"Cor", value=v['cor'], key=f"e_c_{v['id']}")
                                    e_chip = vc5.text_input(f"Chip/Equipamento", value=v.get('info_chip', ''), key=f"e_ch_{v['id']}")
                                    
                                    veiculos_editados.append({"id": v['id'], "tipo": e_tipo, "placa": e_placa, "modelo": e_modelo, "cor": e_cor, "info_chip": e_chip})
                            else:
                                st.info("Este cliente ainda não possui nenhum veículo cadastrado.")

                            st.markdown("---")
                            st.write("➕ **Adicionar Novos Veículos a Este Cliente:**")
                            
                            if f"novos_v_{id_c_sel}" not in st.session_state:
                                st.session_state[f"novos_v_{id_c_sel}"] = 0
                                
                            col_add1, col_add2 = st.columns([1, 4])
                            with col_add1:
                                if st.button("➕ Novo Veículo", type="secondary", key=f"btn_add_nv_{id_c_sel}"):
                                    st.session_state[f"novos_v_{id_c_sel}"] += 1
                                    st.rerun()
                            with col_add2:
                                if st.session_state[f"novos_v_{id_c_sel}"] > 0:
                                    if st.button("➖ Remover Último", type="secondary", key=f"btn_rem_nv_{id_c_sel}"):
                                        st.session_state[f"novos_v_{id_c_sel}"] -= 1
                                        st.rerun()

                            novos_veiculos_dados = []
                            for i in range(st.session_state[f"novos_v_{id_c_sel}"]):
                                st.markdown(f"**Novo Veículo {i+1}**")
                                vc1, vc2, vc3, vc4, vc5 = st.columns([2, 2, 2, 2, 3])
                                n_tipo = vc1.selectbox(f"Tipo ", ["Carro", "Moto", "Caminhão", "Outro"], key=f"n_t_{i}_{id_c_sel}")
                                n_placa = vc2.text_input(f"Placa * ", key=f"n_p_{i}_{id_c_sel}")
                                n_modelo = vc3.text_input(f"Modelo ", key=f"n_m_{i}_{id_c_sel}")
                                n_cor = vc4.text_input(f"Cor ", key=f"n_c_{i}_{id_c_sel}")
                                n_chip = vc5.text_input(f"Chip/Equipamento ", key=f"n_ch_{i}_{id_c_sel}")
                                novos_veiculos_dados.append({"tipo": n_tipo, "placa": n_placa, "modelo": n_modelo, "cor": n_cor, "info_chip": n_chip})

                            st.markdown("<br>", unsafe_allow_html=True)
                            
                            col_salvar1, col_salvar2 = st.columns(2)
                            if col_salvar1.button("💾 Salvar Todas as Alterações", type="primary", key=f"btn_salvar_edit_{id_c_sel}"):
                                execute_query("UPDATE clientes SET nome=%s, documento=%s, endereco=%s, telefone=%s WHERE id=%s", (en_nome, en_doc, en_end, en_tel, id_c_sel))
                                
                                for v_ed in veiculos_editados:
                                    execute_query("UPDATE veiculos SET tipo_veic=%s, placa=%s, modelo=%s, cor=%s, info_chip=%s WHERE id=%s", (v_ed['tipo'], v_ed['placa'], v_ed['modelo'], v_ed['cor'], v_ed['info_chip'], v_ed['id']))
                                
                                validos_novos = [nv for nv in novos_veiculos_dados if nv['placa'].strip()]
                                for nv in validos_novos:
                                    execute_query("INSERT INTO veiculos (cliente_id, tipo_veic, placa, modelo, cor, info_chip) VALUES (%s,%s,%s,%s,%s,%s)", 
                                                    (id_c_sel, nv['tipo'], nv['placa'], nv['modelo'], nv['cor'], nv['info_chip']))
                                    
                                    agora_notif = get_horario_brasil_str()
                                    execute_query("INSERT INTO notificacoes (data_hora, empresa, mensagem) VALUES (%s, %s, %s)", 
                                                  (agora_notif, dados_cliente_sel['empresa'], f"Adicionou um veículo extra ({nv['placa']}) para o cliente {en_nome}."))

                                registrar_auditoria("Edição", "Clientes", f"Dados e veículos do cliente {en_nome} atualizados.", dados_cliente_sel['empresa'])
                                st.session_state.flash_msg = "Cliente e veículos atualizados com sucesso!"
                                st.session_state[f"novos_v_{id_c_sel}"] = 0
                                limpar_tela()
                                st.rerun()
                                
                            if col_salvar2.button("❌ Cancelar / Fechar", key=f"btn_cancel_edit_{id_c_sel}"):
                                limpar_tela()
                                st.rerun()

                    elif acao_clientes == "Excluir":
                        clientes_selecionados = st.multiselect("Selecione um ou mais Clientes para Excluir:", opcoes_cli, key=f"ms_excluir_cli_{k_edit_cli}")
                        
                        if clientes_selecionados:
                            st.warning("⚠️ **Atenção:** Excluir estes clientes removerá os cadastros e TODOS os veículos vinculados a eles!")
                            if st.button("🗑️ Confirmar Exclusão Múltipla"):
                                ids_para_excluir = [int(c.split(" - ")[0]) for c in clientes_selecionados]
                                if ids_para_excluir:
                                    ids_tuple = tuple(ids_para_excluir)
                                    
                                    empresas_afetadas = fetch_data("SELECT DISTINCT empresa FROM clientes WHERE id IN %s", (ids_tuple,))
                                    nomes_empresas = ", ".join([e['empresa'] for e in empresas_afetadas]) if empresas_afetadas else ""

                                    conn = get_conn_fast()
                                    cur = conn.cursor()
                                    cur.execute("DELETE FROM veiculos WHERE cliente_id IN %s", (ids_tuple,))
                                    cur.execute("DELETE FROM clientes WHERE id IN %s", (ids_tuple,))
                                    conn.commit()
                                    st.cache_data.clear()
                                    
                                    registrar_auditoria("Exclusão", "Clientes", f"{len(ids_para_excluir)} cliente(s) e frotas excluídos em lote.", nomes_empresas)
                                    st.session_state.flash_msg = f"{len(ids_para_excluir)} cliente(s) excluído(s) com sucesso!"
                                    limpar_tela()
                                    st.rerun()
                else:
                    st.warning("Nenhum cliente encontrado com este termo.")
        
        elif acao_clientes == "Solicitar Exclusão":
            st.info("Para remover um cliente ou excluir uma placa da sua base, clique no botão abaixo para solicitar a exclusão junto ao suporte oficial informando a placa e o motivo.")
            st.markdown(gerar_link_whatsapp(f"Solicitação de Exclusão de Cadastro - Parceiro: {st.session_state.nome_empresa}"), unsafe_allow_html=True)

    # --- TELA: RELATÓRIOS ---
    elif aba_ativa == "relatorios":
        st.header("📖 Relatórios Operacionais")
        
        if st.session_state.is_admin:
            servico_atual = "Ambos (Furto/Roubo + Monitoramento)"
        else:
            res_servico = fetch_data("SELECT servicos FROM empresas WHERE nome=%s", (st.session_state.nome_empresa,))
            if res_servico and res_servico[0].get('servicos'):
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
                    b_fr = col_f1.text_input("🔍 Busca Inteligente (Nome, Placa ou CPF):", key=f"b_fr_{st.session_state.rk}")
                    p_fr = col_f2.text_input("📅 Filtrar por Data (Furto/Roubo)", key=f"p_fr_{st.session_state.rk}")
                    
                    q_fr = "SELECT * FROM historico WHERE tipo IN ('Furto', 'Roubo')"
                    p_list_fr = []
                    if not st.session_state.is_admin:
                        q_fr += " AND empresa=%s"
                        p_list_fr.append(st.session_state.nome_empresa)
                    if b_fr and len(b_fr) >= 3:
                        q_fr += " AND (cliente ILIKE %s OR placa ILIKE %s)"
                        p_list_fr.extend([f"%{b_fr}%", f"%{b_fr}%"])
                    if p_fr:
                        q_fr += " AND data_hora LIKE %s"
                        p_list_fr.append(f"%{p_fr}%")
                    q_fr += " ORDER BY id DESC"
                    
                    res_fr = fetch_data(q_fr, tuple(p_list_fr))
                    
                    if res_fr:
                        df_fr = pd.DataFrame(res_fr)
                        st.dataframe(df_fr[['id', 'data_hora', 'cliente', 'placa', 'tipo', 'status']], use_container_width=True)
                        
                        st.markdown("### 🔎 Ficha e Finalização de Ocorrência")
                        lista_sel_fr = [""] + [f"{h['id']} - Placa: {h['placa']} - Cliente: {h['cliente']} ({h['data_hora']})" for h in res_fr]
                        
                        k_rel_fr = st.session_state.reset_keys['rel_fr']
                        reg_sel_fr = st.selectbox("Selecione um atendimento para visualizar ou finalizar:", lista_sel_fr, key=f"sb_rel_fr_{k_rel_fr}")
                        
                        if reg_sel_fr != "":
                            id_r = int(reg_sel_fr.split(" - ")[0])
                            dados_fr = next(item for item in res_fr if item["id"] == id_r)
                            
                            col_b1, col_b2 = st.columns([1, 4])
                            with col_b1:
                                if st.button("❌ Fechar Ficha", key="fechar_fr_btn"):
                                    limpar_tela()
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
                                st.write("🟢 **Finalizar Atendimento:**")
                                desfecho = st.text_area("Informe o desfecho do caso (ex: Veículo recuperado com sucesso)", key=f"desfecho_{id_r}")
                                if st.button("✅ Concluir e Finalizar Ocorrência", key=f"btn_concluir_fr_{id_r}"):
                                    agora = get_horario_brasil()
                                    try:
                                        dt_abertura = datetime.strptime(dados_fr['data_hora'], "%d/%m/%Y %H:%M:%S")
                                        dt_abertura = dt_abertura.replace(tzinfo=timezone(timedelta(hours=-3)))
                                        tempo_decorrido = agora - dt_abertura
                                        horas, resto = divmod(tempo_decorrido.total_seconds(), 3600)
                                        minutos, _ = divmod(resto, 60)
                                        sla_str = f"{int(horas)}h e {int(minutos)}m"
                                    except Exception:
                                        sla_str = "Não calculado"

                                    protocolo = f"AD-{id_r}-{agora.strftime('%Y%m%d%H%M')}"
                                    novo_detalhe = dados_fr['detalhes'] + f" | DESFECHO: {desfecho} | SLA DE RESPOSTA: {sla_str} | PROTOCOLO: {protocolo}"
                                    
                                    execute_query("UPDATE historico SET status='FINALIZADO', detalhes=%s WHERE id=%s", (novo_detalhe, id_r))
                                    registrar_auditoria("Finalização", "Operação", f"Ocorrência ID {id_r} finalizada. Protocolo: {protocolo}", dados_fr['empresa'])
                                    st.session_state.flash_msg = "Ocorrência finalizada e protocolada com sucesso!"
                                    limpar_tela()
                                    st.rerun()
                            
                            st.markdown("<br>", unsafe_allow_html=True)
                            st.markdown(gerar_relatorio_html(dados_fr, st.session_state.nome_empresa), unsafe_allow_html=True)
                    else:
                        st.info("Nenhum registro de Furto ou Roubo encontrado.")
                idx_sub += 1

            if mostrar_mon:
                with sub_tabs[idx_sub]:
                    st.subheader("Eventos de Monitoramento Técnico e Transferências")
                    col_m1, col_m2 = st.columns(2)
                    b_mon = col_m1.text_input("🔍 Busca Inteligente (Nome, Placa ou CPF):", key=f"b_mon_{st.session_state.rk}")
                    p_mon = col_m2.text_input("📅 Filtrar por Data", key=f"p_mon_{st.session_state.rk}")
                    
                    q_mon = "SELECT * FROM historico WHERE tipo IN ('Monitoramento', 'Transferência')"
                    p_list_mon = []
                    if not st.session_state.is_admin:
                        q_mon += " AND empresa=%s"
                        p_list_mon.append(st.session_state.nome_empresa)
                    if b_mon and len(b_mon) >= 3:
                        q_mon += " AND (cliente ILIKE %s OR placa ILIKE %s)"
                        p_list_mon.extend([f"%{b_mon}%", f"%{b_mon}%"])
                    if p_mon:
                        q_mon += " AND data_hora LIKE %s"
                        p_list_mon.append(f"%{p_mon}%")
                    q_mon += " ORDER BY id DESC"
                    
                    res_mon = fetch_data(q_mon, tuple(p_list_mon))
                    
                    if res_mon:
                        df_mon = pd.DataFrame(res_mon)
                        st.dataframe(df_mon[['id', 'data_hora', 'cliente', 'placa', 'tipo', 'status']], use_container_width=True)
                        
                        st.markdown("### 🔎 Ficha de Relatório")
                        
                        lista_sel_mon = [""] + [f"{h['id']} - Placa: {h['placa']} - Cliente: {h['cliente']} ({h['data_hora']})" for h in res_mon]
                        
                        k_rel_mon = st.session_state.reset_keys['rel_mon']
                        reg_sel_mon = st.selectbox("Selecione um registro para visualizar:", lista_sel_mon, key=f"sb_rel_mon_{k_rel_mon}")
                        
                        if reg_sel_mon != "":
                            id_m = int(reg_sel_mon.split(" - ")[0])
                            dados_mon = next(item for item in res_mon if item["id"] == id_m)
                            
                            col_mb1, col_mb2 = st.columns([1, 4])
                            with col_mb1:
                                if st.button("❌ Fechar Ficha", key="fechar_mon_btn"):
                                    limpar_tela()
                                    st.rerun()

                            st.markdown(f'''
                            <div class="ficha-box">
                                <h4 style="color:#4a0e4e; text-align:center;">Ficha de Monitoramento / Transferência nº {dados_mon['id']}</h4>
                                <hr>
                                <p><b>Data/Hora:</b> {dados_mon['data_hora']}</p>
                                <p><b>Cliente:</b> {dados_mon['cliente']}</p>
                                <p><b>Placa:</b> {dados_mon['placa']}</p>
                                <p><b>Status:</b> {dados_mon['status']}</p>
                                <hr>
                                <p><b>Detalhes / Ação da Central / Resolução:</b></p>
                                <p>{dados_mon['detalhes']}</p>
                            </div>
                            ''', unsafe_allow_html=True)
                            
                            st.markdown("<br>", unsafe_allow_html=True)
                            st.markdown(gerar_relatorio_html(dados_mon, st.session_state.nome_empresa), unsafe_allow_html=True)
                    else:
                        st.info("Nenhum registro encontrado.")
                idx_sub += 1

    # --- TELA: MEU FATURAMENTO (SÓ PARCEIROS) ---
    elif aba_ativa == "faturamento" and not st.session_state.is_admin:
        st.header("💰 Meu Faturamento e Frotas Ativas")
        
        res_emp_info = fetch_data("SELECT servicos, valor_veiculo, dia_vencimento, status_pagamento, valor_pago FROM empresas WHERE nome=%s", (st.session_state.nome_empresa,))
        
        if res_emp_info:
            servico_emp = res_emp_info[0]['servicos'] if res_emp_info[0].get('servicos') else "Ambos"
            valor_por_veiculo = res_emp_info[0]['valor_veiculo'] if res_emp_info[0].get('valor_veiculo') is not None else 3.00
            dia_venc = res_emp_info[0]['dia_vencimento'] if res_emp_info[0].get('dia_vencimento') is not None else 10
            status_pag = res_emp_info[0]['status_pagamento'] if res_emp_info[0].get('status_pagamento') else "Pendente"
            valor_pago_efetivo = res_emp_info[0]['valor_pago'] if res_emp_info[0].get('valor_pago') is not None else 0.00
        else:
            servico_emp = "Ambos"
            valor_por_veiculo = 3.00
            dia_venc = 10
            status_pag = "Pendente"
            valor_pago_efetivo = 0.00
        
        status_visual = calcular_status_fatura(status_pag, dia_venc)

        if status_visual == "🔴 Vencida / Atrasada":
            msg_html = f"<div style='padding: 10px; border-radius: 5px; background-color: #ffebee; color: #c62828; font-size: 13px; margin-bottom: 10px;'>⚠️ <b>ATENÇÃO - FATURA ATRASADA:</b> Sua fatura venceu e encontra-se em atraso. Serviços temporariamente suspensos até a quitação.</div>"
        elif status_visual == "🟠 Vence Hoje":
            msg_html = f"<div style='padding: 10px; border-radius: 5px; background-color: #fff3e0; color: #e65100; font-size: 13px; margin-bottom: 10px;'>⚠️ <b>AVISO FINANCEIRO:</b> Sua fatura referente ao fechamento do último mês vence hoje. Evite bloqueios realizando o pagamento.</div>"
        elif status_visual == "🟡 Fatura Fechada (Próxima ao Vencimento)":
            msg_html = f"<div style='padding: 10px; border-radius: 5px; background-color: #fffde7; color: #f57f17; font-size: 13px; margin-bottom: 10px;'>🔔 <b>Aviso Financeiro:</b> Sua fatura foi fechada (corte de 2 dias antes do vencimento dia {dia_venc}). Fique atento.</div>"
        else:
            msg_html = f"<div style='padding: 10px; border-radius: 5px; background-color: #e8f5e9; color: #2e7d32; font-size: 13px; margin-bottom: 10px;'>✅ <b>Situação Financeira Regularizada:</b> Suas faturas encontram-se em dia. Obrigado por manter sua parceria conosco!</div>"
        
        st.markdown(msg_html, unsafe_allow_html=True)
        st.markdown(f"<p style='font-size: 13px; color: #555; margin-bottom: 20px;'>ℹ️ <b>Pacote Contratado:</b> {servico_emp} | <b>Vencimento:</b> Todo dia {dia_venc} do mês</p>", unsafe_allow_html=True)
        
        q_conta_veic = "SELECT count(v.id) as total_veiculos FROM veiculos v JOIN clientes c ON v.cliente_id = c.id WHERE c.empresa = %s AND c.status = 'Ativo'"
        res_conta = fetch_data(q_conta_veic, (st.session_state.nome_empresa,))
        total_veiculos = res_conta[0]['total_veiculos'] if res_conta else 0
        
        valor_total_fatura = total_veiculos * valor_por_veiculo
        
        html_kpis = f"""
        <div style="display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 20px;">
            <div style="flex: 1; min-width: 150px; padding: 15px; background: #f9f9f9; border-radius: 8px; border-left: 4px solid #4a0e4e;">
                <p style="margin: 0; font-size: 13px; color: #666;">🚗 Veículos Ativos</p>
                <h3 style="margin: 5px 0 0 0; color: #333; font-size: 22px;">{total_veiculos}</h3>
            </div>
            <div style="flex: 1; min-width: 150px; padding: 15px; background: #f9f9f9; border-radius: 8px; border-left: 4px solid #4a0e4e;">
                <p style="margin: 0; font-size: 13px; color: #666;">💵 Valor Unitário</p>
                <h3 style="margin: 5px 0 0 0; color: #333; font-size: 22px;">R$ {valor_por_veiculo:.2f}</h3>
            </div>
            <div style="flex: 1; min-width: 150px; padding: 15px; background: #f9f9f9; border-radius: 8px; border-left: 4px solid #4a0e4e;">
                <p style="margin: 0; font-size: 13px; color: #666;">💳 Faturamento Previsto</p>
                <h3 style="margin: 5px 0 0 0; color: #333; font-size: 22px;">R$ {valor_total_fatura:.2f}</h3>
            </div>
            <div style="flex: 1; min-width: 150px; padding: 15px; background: #f9f9f9; border-radius: 8px; border-left: 4px solid #8b0000;">
                <p style="margin: 0; font-size: 13px; color: #666;">📌 Status da Fatura</p>
                <h3 style="margin: 5px 0 0 0; color: #8b0000; font-size: 18px;">{status_visual}</h3>
            </div>
        </div>
        """
        st.markdown(html_kpis, unsafe_allow_html=True)

        if status_pag == "Pago":
            st.markdown(f"<p style='font-size: 13px; color: #555;'>💡 <b>Valor Quitado Registrado no Mês:</b> R$ {valor_pago_efetivo:.2f}</p>", unsafe_allow_html=True)
        
        st.markdown("---")
        st.subheader("🔍 Consulta Histórica de Faturas")
        
        res_meses_p = fetch_data("SELECT DISTINCT mes_ref FROM historico_faturas WHERE empresa=%s ORDER BY mes_ref DESC", (st.session_state.nome_empresa,))
        lista_meses_p = ["Selecione..."] + [m['mes_ref'] for m in res_meses_p] if res_meses_p else ["Selecione..."]
        
        mes_busca_parceiro = st.selectbox("Filtrar por Mês/Ano:", lista_meses_p, key=f"sel_mes_p_{st.session_state.rk}")
        digita_mes_p = st.text_input("Ou digite o mês (Ex: 06/2026):", value="", key=f"dig_mes_p_{st.session_state.rk}")
        
        mes_alvo_p = digita_mes_p.strip() if digita_mes_p.strip() else (mes_busca_parceiro if mes_busca_parceiro != "Selecione..." else "")

        if mes_alvo_p:
            res_hist_p = fetch_data("SELECT * FROM historico_faturas WHERE empresa=%s AND mes_ref=%s", (st.session_state.nome_empresa, mes_alvo_p))
            if res_hist_p:
                df_hp = pd.DataFrame(res_hist_p)[['mes_ref', 'total_veiculos', 'valor_unitario', 'valor_fatura_calculada', 'valor_pago', 'status', 'data_pagamento']]
                df_hp.columns = ['Mês Ref.', 'Veículos', 'Valor Unit.', 'Fatura Calc.', 'Valor Pago', 'Status', 'Data Pgto']
                st.dataframe(df_hp, use_container_width=True)
            else:
                st.info(f"Nenhum registro encontrado para o mês {mes_alvo_p}.")

    elif aba_ativa == "cadastro" and not st.session_state.is_admin:
        st.header("⚙️ Meu Cadastro Profissional")
        st.markdown("<p style='font-size: 13px; color: #666;'>Mantenha seus dados de contato e endereço atualizados para garantir a comunicação correta com a Central.</p>", unsafe_allow_html=True)
        
        res_emp = fetch_data("SELECT * FROM empresas WHERE nome=%s", (st.session_state.nome_empresa,))
        if res_emp:
            dados_emp = res_emp[0]
            val_veic = dados_emp['valor_veiculo'] if dados_emp['valor_veiculo'] is not None else 0.0
            dia_v = dados_emp['dia_vencimento'] if dados_emp['dia_vencimento'] is not None else 10
            
            st.markdown("### 🔒 Informações Contratuais")
            
            html_readonly = f"""
            <div style="background-color: #fafafa; border-left: 4px solid #4a0e4e; border-radius: 4px; padding: 15px; margin-bottom: 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
                    <div>
                        <span style="color: #8b0000; font-size: 11px; font-weight: bold; text-transform: uppercase;">Empresa / Login</span><br>
                        <span style="color: #333; font-size: 14px; font-weight: 500;">{dados_emp['nome']}</span>
                    </div>
                    <div>
                        <span style="color: #8b0000; font-size: 11px; font-weight: bold; text-transform: uppercase;">CNPJ</span><br>
                        <span style="color: #333; font-size: 14px; font-weight: 500;">{dados_emp['cnpj']}</span>
                    </div>
                    <div>
                        <span style="color: #8b0000; font-size: 11px; font-weight: bold; text-transform: uppercase;">Serviços</span><br>
                        <span style="color: #333; font-size: 14px; font-weight: 500;">{dados_emp['servicos']}</span>
                    </div>
                    <div>
                        <span style="color: #8b0000; font-size: 11px; font-weight: bold; text-transform: uppercase;">Valor por Veículo</span><br>
                        <span style="color: #333; font-size: 14px; font-weight: 500;">R$ {val_veic:.2f}</span>
                    </div>
                    <div>
                        <span style="color: #8b0000; font-size: 11px; font-weight: bold; text-transform: uppercase;">Dia de Vencimento</span><br>
                        <span style="color: #333; font-size: 14px; font-weight: 500;">Dia {dia_v}</span>
                    </div>
                </div>
            </div>
            """
            st.markdown(html_readonly, unsafe_allow_html=True)
            
            st.markdown("### 📝 Atualização de Dados de Contato")
            
            with st.form("form_atualizacao_cadastral"):
                c1, c2 = st.columns(2)
                c_resp = c1.text_input("Nome do Responsável", value=dados_emp.get('responsavel', ''))
                c_tel = c2.text_input("Telefone Corporativo / WhatsApp", value=dados_emp.get('telefone', ''))
                c_email = c1.text_input("E-mail Profissional", value=dados_emp.get('email', ''))
                c_end = c2.text_input("Endereço Completo", value=dados_emp.get('endereco', ''))
                
                st.markdown("<br>", unsafe_allow_html=True)
                if st.form_submit_button("💾 Salvar Alterações Cadastrais", type="primary"):
                    execute_query("UPDATE empresas SET responsavel=%s, telefone=%s, email=%s, endereco=%s WHERE nome=%s", 
                                  (c_resp, c_tel, c_email, c_end, st.session_state.nome_empresa))
                    
                    registrar_auditoria("Edição", "Cadastro Parceiro", "Atualizou dados cadastrais profissionais (Endereço/Contato).", st.session_state.nome_empresa)
                    st.session_state.flash_msg = "Dados atualizados com sucesso!"
                    limpar_tela()
                    st.rerun()
        else:
            st.error("Erro ao localizar cadastro da empresa.")

    elif aba_ativa == "empresas" and st.session_state.is_admin:
        st.header("🏢 Gerenciamento de Empresas Parceiras e Precificação")
        
        acao_parceiros = st.radio("Ação Empresas:", ["Listar", "Incluir Nova", "Editar", "Excluir"], horizontal=True)
        st.markdown("---")
        
        empresas_res = fetch_data("SELECT id, nome, cnpj, endereco, telefone, email, responsavel, servicos, valor_veiculo, dia_vencimento, status_pagamento, valor_pago FROM empresas ORDER BY nome")
        df_empresas = pd.DataFrame(empresas_res) if empresas_res else pd.DataFrame()
        
        if acao_parceiros == "Listar":
            if not df_empresas.empty:
                for _, emp in df_empresas.iterrows():
                    with st.expander(f"📁 Empresa: {emp['nome']}"):
                        st.write(f"**Responsável:** {emp['responsavel']}")
                        e_mail_disp = emp['email'] if emp['email'] else "Não informado"
                        st.write(f"**Telefone:** {emp['telefone']} | **E-mail:** {e_mail_disp} | **Endereço:** {emp['endereco']}")
                        servico_vinculado = emp['servicos'] if 'servicos' in emp and emp['servicos'] else "Ambos (Furto/Roubo + Monitoramento)"
                        valor_unit = emp['valor_veiculo'] if ('valor_veiculo' in emp and emp['valor_veiculo'] is not None) else 3.00
                        dia_v = emp['dia_vencimento'] if ('dia_vencimento' in emp and emp['dia_vencimento'] is not None) else 10
                        stat_pag = emp['status_pagamento'] if ('status_pagamento' in emp and emp['status_pagamento'] is not None) else "Pendente"
                        val_pago_ef = emp['valor_pago'] if ('valor_pago' in emp and emp['valor_pago'] is not None) else 0.00
                        
                        st.write(f"**Pacote:** {servico_vinculado} | **Preço/Veículo:** R$ {valor_unit:.2f} | **Vencimento:** Dia {dia_v}")
                        st.write(f"**Status Fatura Atual:** {stat_pag} | **Valor Pago Registrado:** R$ {val_pago_ef:.2f}")
            else:
                st.info("Nenhuma empresa parceira cadastrada.")
        
        elif acao_parceiros == "Incluir Nova":
            with st.form("nova_empresa", clear_on_submit=True):
                e_nome = st.text_input("Nome da Empresa (Será o Login) *")
                e_cnpj = st.text_input("CNPJ/Senha Inicial *")
                e_end = st.text_input("Endereço")
                e_tel = st.text_input("Telefone")
                e_email = st.text_input("E-mail")
                e_resp = st.text_input("Responsável")
                e_servicos = st.selectbox("Serviços Contratados", ["Ambos (Furto/Roubo + Monitoramento)", "Apenas Furto e Roubo", "Apenas Monitoramento"])
                e_valor = st.number_input("Valor por Veículo (R$) *", min_value=0.0, value=3.00, format="%.2f")
                e_venc = st.number_input("Dia de Vencimento da Fatura *", min_value=1, max_value=31, value=10)
                
                if st.form_submit_button("Registrar Parceiro"):
                    if e_nome and e_cnpj:
                        senha_hash = hash_senha(e_cnpj)
                        execute_query("INSERT INTO empresas (nome, cnpj, senha, endereco, telefone, email, responsavel, servicos, valor_veiculo, dia_vencimento, status_pagamento, valor_pago) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", 
                                      (e_nome, e_cnpj, senha_hash, e_end, e_tel, e_email, e_resp, e_servicos, e_valor, e_venc, 'Pendente', 0.00))
                        registrar_auditoria("Cadastro", "Parceiros", f"Empresa {e_nome} criada. Pacote: {e_servicos} | R$ {e_valor:.2f} | Venc. Dia {e_venc}.", e_nome)
                        st.session_state.flash_msg = "Empresa cadastrada com sucesso e tela limpa!"
                        limpar_tela()
                        st.rerun()
                    else:
                        st.error("Nome e CNPJ são obrigatórios.")
                        
        elif acao_parceiros in ["Editar", "Excluir"]:
            if empresas_res:
                lista_opcoes_e = [f"{e['id']} - {e['nome']}" for e in empresas_res]
                
                k_edit_emp = st.session_state.reset_keys['edit_emp']
                emp_selecionada = st.selectbox("🔍 Selecione a Empresa na lista:", [""] + lista_opcoes_e, key=f"sb_edit_emp_{k_edit_emp}")
                
                if emp_selecionada:
                    if st.button("❌ Fechar Seleção", key="btn_close_edit_emp"):
                        limpar_tela()
                        st.rerun()

                    id_emp = int(emp_selecionada.split(" - ")[0])
                    dados_e = next(item for item in empresas_res if item["id"] == id_emp)
                    
                    if acao_parceiros == "Editar":
                        with st.form(f"form_edit_emp_{id_emp}", clear_on_submit=True):
                            ne_nome = st.text_input("Nome", value=dados_e['nome'])
                            ne_cnpj = st.text_input("CNPJ (Se precisar corrigir)", value=dados_e['cnpj'])
                            ne_resp = st.text_input("Responsável", value=dados_e['responsavel'])
                            ne_tel = st.text_input("Telefone", value=dados_e['telefone'])
                            ne_email = st.text_input("E-mail", value=dados_e.get('email', ''))
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
                                execute_query("UPDATE empresas SET nome=%s, cnpj=%s, responsavel=%s, telefone=%s, email=%s, endereco=%s, servicos=%s, valor_veiculo=%s, dia_vencimento=%s WHERE id=%s", 
                                              (ne_nome, ne_cnpj, ne_resp, ne_tel, ne_email, ne_end, ne_servicos, ne_valor, ne_venc, id_emp))
                                registrar_auditoria("Edição", "Parceiros", f"Parceiro ID {id_emp} alterado. Preço: R$ {ne_valor:.2f} | Venc. Dia {ne_venc}", ne_nome)
                                st.session_state.flash_msg = "Alterações salvas com sucesso!"
                                limpar_tela()
                                st.rerun()
                    
                    elif acao_parceiros == "Excluir":
                        st.warning(f"Tem certeza que deseja excluir a empresa **{dados_e['nome']}**?")
                        if st.button("🗑️ Excluir Parceiro"):
                            execute_query("DELETE FROM empresas WHERE id=%s", (id_emp,))
                            registrar_auditoria("Exclusão", "Parceiros", f"Parceiro ID {id_emp} excluído.", dados_e['nome'])
                            st.session_state.flash_msg = "Empresa excluída com sucesso!"
                            limpar_tela()
                            st.rerun()
            else:
                st.warning("Nenhuma empresa encontrada.")

    elif aba_ativa == "financeiro" and st.session_state.is_admin:
        st.header("💰 Controle Financeiro Global")
        st.markdown("<p style='font-size: 13px; color: #666;'>Painel executivo financeiro com o faturamento acumulado de todas as frotas ativas na base.</p>", unsafe_allow_html=True)
        
        empresas_cad = fetch_data("SELECT id, nome, cnpj, valor_veiculo, dia_vencimento, status_pagamento, valor_pago FROM empresas ORDER BY nome")
        
        q_v_global = "SELECT c.empresa, count(v.id) as qtd FROM veiculos v JOIN clientes c ON v.cliente_id = c.id WHERE c.status = 'Ativo' GROUP BY c.empresa"
        res_v_global = fetch_data(q_v_global)
        
        mapa_qtd_veiculos = {item['empresa']: item['qtd'] for item in res_v_global} if res_v_global else {}
        
        total_faturamento_previsto = 0.0
        total_atrasado = 0.0
        total_pago = 0.0
        
        dados_financeiro_global = []
        if empresas_cad:
            for emp in empresas_cad:
                nome_emp = emp['nome']
                val_unit = emp['valor_veiculo'] if emp['valor_veiculo'] is not None else 3.00
                dia_venc = emp['dia_vencimento'] if emp['dia_vencimento'] is not None else 10
                stat_p = emp['status_pagamento'] if emp['status_pagamento'] is not None else "Pendente"
                v_pago_ef = emp['valor_pago'] if emp['valor_pago'] is not None else 0.00
                
                status_calculado = calcular_status_fatura(stat_p, dia_venc)
                
                qtd_v = mapa_qtd_veiculos.get(nome_emp, 0)
                valor_calc = qtd_v * val_unit
                
                total_faturamento_previsto += valor_calc
                
                if "Pago" in status_calculado:
                    pass
                if "Vencida" in status_calculado or "Vence Hoje" in status_calculado:
                    total_atrasado += valor_calc
                    
                total_pago += v_pago_ef
                
                dados_financeiro_global.append({
                    "Empresa Parceira": nome_emp,
                    "Veículos Ativos": qtd_v,
                    "Valor Unitário": f"R$ {val_unit:.2f}",
                    "Vencimento": f"Dia {dia_venc}",
                    "Faturamento Previsto": f"R$ {valor_calc:.2f}",
                    "Valor Pago Registrado": f"R$ {v_pago_ef:.2f}",
                    "Status Atual": status_calculado
                })
        
        html_kpis_adm = f"""
        <div style="display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 20px;">
            <div style="flex: 1; min-width: 200px; padding: 15px; background: #f9f9f9; border-radius: 8px; border-left: 4px solid #4a0e4e;">
                <p style="margin: 0; font-size: 13px; color: #666;">💵 Faturamento Previsto (Ativos)</p>
                <h3 style="margin: 5px 0 0 0; color: #333; font-size: 22px;">R$ {total_faturamento_previsto:.2f}</h3>
            </div>
            <div style="flex: 1; min-width: 200px; padding: 15px; background: #f9f9f9; border-radius: 8px; border-left: 4px solid #c62828;">
                <p style="margin: 0; font-size: 13px; color: #666;">🔴 Valor Atrasado / Vencido</p>
                <h3 style="margin: 5px 0 0 0; color: #c62828; font-size: 22px;">R$ {total_atrasado:.2f}</h3>
            </div>
            <div style="flex: 1; min-width: 200px; padding: 15px; background: #f9f9f9; border-radius: 8px; border-left: 4px solid #2e7d32;">
                <p style="margin: 0; font-size: 13px; color: #666;">🟢 Valor Pago Registrado</p>
                <h3 style="margin: 5px 0 0 0; color: #2e7d32; font-size: 22px;">R$ {total_pago:.2f}</h3>
            </div>
        </div>
        """
        st.markdown(html_kpis_adm, unsafe_allow_html=True)
        
        if empresas_cad:
            df_fin_global = pd.DataFrame(dados_financeiro_global)
            st.dataframe(df_fin_global, use_container_width=True)
            
            st.markdown("---")
            st.subheader("🔍 Consulta Histórica de Faturas")
            
            res_meses_db = fetch_data("SELECT DISTINCT mes_ref FROM historico_faturas ORDER BY mes_ref DESC")
            lista_meses_adm = ["Todos"] + [m['mes_ref'] for m in res_meses_db] if res_meses_db else ["Todos"]
            
            col_h1, col_h2 = st.columns(2)
            mes_busca_admin = col_h1.selectbox("Filtrar por Mês/Ano:", lista_meses_adm, key=f"hist_mes_{st.session_state.rk}")
            digita_mes_adm = col_h2.text_input("Ou digite o mês (Ex: 06/2026):", value="", key=f"hist_dig_{st.session_state.rk}")
            
            emp_filtro_adm = st.selectbox("Filtrar por Empresa:", ["Todas"] + [e['nome'] for e in empresas_cad], key=f"hist_emp_{st.session_state.rk}")

            mes_alvo_adm = digita_mes_adm.strip() if digita_mes_adm.strip() else (mes_busca_admin if mes_busca_admin != "Todos" else "")

            q_hist_adm = "SELECT * FROM historico_faturas WHERE 1=1"
            p_hist_adm = []
            if mes_alvo_adm:
                q_hist_adm += " AND mes_ref = %s"
                p_hist_adm.append(mes_alvo_adm)
            if emp_filtro_adm != "Todas":
                q_hist_adm += " AND empresa = %s"
                p_hist_adm.append(emp_filtro_adm)
            
            res_hist_adm = fetch_data(q_hist_adm, tuple(p_hist_adm))
            if res_hist_adm:
                df_hadm = pd.DataFrame(res_hist_adm)[['mes_ref', 'empresa', 'total_veiculos', 'valor_unitario', 'valor_fatura_calculada', 'valor_pago', 'status', 'data_pagamento']]
                df_hadm.columns = ['Mês Ref.', 'Empresa', 'Veículos', 'Valor Unit.', 'Fatura Calc.', 'Valor Pago', 'Status', 'Data Pgto']
                st.dataframe(df_hadm, use_container_width=True)
            else:
                st.info("Nenhum histórico de fatura encontrado para os filtros selecionados.")

            st.markdown("---")
            st.subheader("⚡ Atualizar Pagamento e Valor da Fatura")
            
            k_fin = st.session_state.reset_keys['fin_pgto']
            lista_p_nomes = [e['nome'] for e in empresas_cad]
            emp_escolhida_pagto = st.selectbox("Selecione a Empresa Parceira:", [""] + lista_p_nomes, key=f"sel_fin_emp_{k_fin}")
            
            if emp_escolhida_pagto != "":
                if st.button("❌ Cancelar / Limpar Seleção", key="btn_close_fin"):
                    limpar_tela()
                    st.rerun()
                    
                dados_emp_fin = next(item for item in empresas_cad if item["nome"] == emp_escolhida_pagto)
                val_atual = dados_emp_fin['valor_veiculo'] if dados_emp_fin['valor_veiculo'] is not None else 3.00
                stat_atual = dados_emp_fin['status_pagamento'] if dados_emp_fin['status_pagamento'] is not None else "Pendente"
                vp_atual = dados_emp_fin['valor_pago'] if dados_emp_fin['valor_pago'] is not None else 0.00
                
                qtd_v_calc = mapa_qtd_veiculos.get(emp_escolhida_pagto, 0)
                
                with st.form("form_atualiza_status_pagto", clear_on_submit=True):
                    st.write(f"**Empresa Selecionada:** {emp_escolhida_pagto}")
                    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                    
                    novo_valor_unit = col_f1.number_input("Novo Valor Unitário:", min_value=0.0, value=float(val_atual), format="%.2f", key=f"fin_v_u_{k_fin}")
                    novo_valor_pago = col_f2.number_input("Valor Total Pago:", min_value=0.0, value=float(vp_atual), format="%.2f", key=f"fin_v_p_{k_fin}")
                    
                    data_atual = get_horario_brasil()
                    mes_passado = data_atual.replace(day=1) - timedelta(days=1)
                    sugestao_mes_ref = mes_passado.strftime("%m/%Y")
                    
                    mes_referencia = col_f3.text_input("Mês Ref. (Ex: 06/2026):", value=sugestao_mes_ref, key=f"fin_m_r_{k_fin}")
                    
                    opcoes_st_fin = ["Pendente", "Pago"]
                    idx_st_fin = opcoes_st_fin.index(stat_atual) if stat_atual in opcoes_st_fin else 0
                    novo_status_pagto = col_f4.selectbox("Status:", opcoes_st_fin, index=idx_st_fin, key=f"fin_st_{k_fin}")
                    
                    if st.form_submit_button("💾 Salvar Pagamento e Registrar Histórico"):
                        execute_query("UPDATE empresas SET status_pagamento=%s, valor_veiculo=%s, valor_pago=%s WHERE nome=%s", (novo_status_pagto, novo_valor_unit, novo_valor_pago, emp_escolhida_pagto))
                        
                        data_pgto_hoje = get_horario_brasil_str()
                        val_fatura_calc = qtd_v_calc * novo_valor_unit
                        
                        execute_query("INSERT INTO historico_faturas (mes_ref, empresa, total_veiculos, valor_unitario, valor_fatura_calculada, valor_pago, status, data_pagamento) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                                      (mes_referencia, emp_escolhida_pagto, qtd_v_calc, novo_valor_unit, val_fatura_calc, novo_valor_pago, novo_status_pagto, data_pgto_hoje))

                        registrar_auditoria("Financeiro", "Faturamento", f"Fatura de {emp_escolhida_pagto} (Mês Ref: {mes_referencia}) alterada para {novo_status_pagto} | Valor Pago: R$ {novo_valor_pago:.2f}", emp_escolhida_pagto)
                        st.session_state.flash_msg = f"Financeiro e Histórico de {emp_escolhida_pagto} atualizados com sucesso!"
                        limpar_tela()
                        st.rerun()

    elif aba_ativa == "auditoria":
        st.header("🕵️ Auditoria e Registros de Atividades")
        st.markdown("<p style='font-size: 13px; color: #666; margin-bottom: 15px;'>🔒 <b>Blindagem Jurídica Ativa:</b> Todos os registros do sistema são inalteráveis e não podem ser apagados, servindo como documento comprobatório oficial da Central de Operações de acordo com a LGPD e Marco Civil da Internet.</p>", unsafe_allow_html=True)
        
        mes_atual_padrao = datetime.now().strftime("%m/%Y")
        filtro_mes_aud = st.text_input("🔍 Busca (Mês/Ano ou Texto):", value=mes_atual_padrao, key=f"aud_b_{st.session_state.rk}")
        
        q_aud = "SELECT * FROM auditoria WHERE 1=1"
        p_aud = []
        
        if not st.session_state.is_admin:
            q_aud += " AND (usuario = %s OR detalhes ILIKE %s)"
            p_aud.extend([st.session_state.nome_empresa, f"%Alvo: {st.session_state.nome_empresa}%"])
            
        if filtro_mes_aud:
            termo = f"%{filtro_mes_aud}%"
            q_aud += " AND (data_hora ILIKE %s OR usuario ILIKE %s OR detalhes ILIKE %s)"
            p_aud.extend([termo, termo, termo])
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
        else:
            st.info(f"Nenhum registro de auditoria para os termos buscados.")
            
        # --- PAINEL EXCLUSIVO DO ADMIN PARA VER ACEITES DA LGPD ---
        if st.session_state.is_admin:
            st.markdown("---")
            st.subheader("📄 Assinaturas Eletrônicas - Aceites LGPD")
            st.markdown("<p style='font-size: 13px; color: #666;'>Aqui ficam registrados todos os parceiros que assinaram e concordaram com o Termo de Responsabilidade e Confidencialidade.</p>", unsafe_allow_html=True)
            
            res_lgpd_adm = fetch_data("SELECT * FROM aceites_lgpd ORDER BY id DESC")
            
            if res_lgpd_adm:
                df_lgpd = pd.DataFrame(res_lgpd_adm)
                df_lgpd_visual = df_lgpd[['id', 'empresa', 'data_hora', 'ip_aceite', 'hash_assinatura']].copy()
                df_lgpd_visual.columns = ['ID', 'Empresa', 'Data/Hora do Aceite', 'Meio de Acesso', 'Hash (Assinatura Eletrônica)']
                st.dataframe(df_lgpd_visual, use_container_width=True)
                
                st.markdown("### 🖨️ Gerar Certificado de Aceite / PDF")
                k_lgpd_cert = st.session_state.reset_keys['lgpd_cert']
                lista_aceites = [""] + [f"{a['id']} - {a['empresa']} ({a['data_hora']})" for a in res_lgpd_adm]
                aceite_sel = st.selectbox("Selecione a assinatura do parceiro:", lista_aceites, key=f"sel_aceite_{k_lgpd_cert}")
                
                if aceite_sel != "":
                    id_a = int(aceite_sel.split(" - ")[0])
                    dados_a = next(item for item in res_lgpd_adm if item["id"] == id_a)
                    
                    cnpj_res = fetch_data("SELECT cnpj FROM empresas WHERE nome=%s", (dados_a['empresa'],))
                    cnpj_parceiro = "Migração / Falta Atualização de Cadastro"
                    if cnpj_res:
                        cnpj_tamanho = len(str(cnpj_res[0]['cnpj']))
                        if cnpj_tamanho == 64:
                            cnpj_parceiro = "Migração (O CNPJ precisa ser corrigido na aba Empresas)"
                        else:
                            cnpj_parceiro = cnpj_res[0]['cnpj']
                        
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(gerar_certificado_lgpd_html(dados_a, cnpj_parceiro), unsafe_allow_html=True)
                    
                    if st.button("❌ Fechar Gerador", key="btn_close_cert"):
                        limpar_tela()
                        st.rerun()
            else:
                st.info("Nenhuma assinatura registrada ainda.")
