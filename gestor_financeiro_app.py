#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
import os
import json
import uuid

DATABASE_URL = os.environ.get('DATABASE_URL')

app = Flask(__name__)

# ======================== BANCO DE DADOS ========================

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Inicializar banco de dados com tabelas"""
    conn = get_conn()
    cursor = conn.cursor()

    # Tabela de Perfil (configurações gerais)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS perfil (
            id INTEGER PRIMARY KEY,
            renda_mensal REAL DEFAULT 0,
            data_atualizacao TEXT
        )
    ''')

    # Tabela de Gastos Essenciais
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_essenciais (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            valor REAL NOT NULL,
            data_criacao TEXT
        )
    ''')

    # Tabela de Dívidas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dividas (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            valor_total REAL NOT NULL,
            taxa_juros REAL DEFAULT 0,
            parcela_mensal REAL NOT NULL,
            status TEXT DEFAULT 'ativa',
            data_criacao TEXT
        )
    ''')

    # Tabela de Gastos Variáveis
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_variaveis (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            valor REAL NOT NULL,
            data_criacao TEXT
        )
    ''')

    # Tabela de Transações Diárias (para rastreamento do dia-a-dia)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transacoes (
            id SERIAL PRIMARY KEY,
            tipo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            descricao TEXT,
            valor REAL NOT NULL,
            data TEXT NOT NULL,
            data_vencimento TEXT,
            recorrente INTEGER DEFAULT 0,
            meses_recorrencia INTEGER DEFAULT 0,
            hora TEXT,
            observacoes TEXT
        )
    ''')

    # Tabela de Pagamentos de Dívidas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pagamentos (
            id SERIAL PRIMARY KEY,
            divida_id INTEGER,
            valor_pago REAL NOT NULL,
            data_pagamento TEXT,
            observacoes TEXT,
            FOREIGN KEY(divida_id) REFERENCES dividas(id)
        )
    ''')

    # Tabela de Receitas Adicionais
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS receitas (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            valor REAL NOT NULL,
            data_criacao TEXT
        )
    ''')

    # Tabela de Empréstimos Pessoais
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emprestimos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            valor REAL NOT NULL,
            data_emprestimo TEXT,
            data_devolucao_esperada TEXT,
            observacoes TEXT,
            data_criacao TEXT
        )
    ''')

    # Tabela de Empréstimos Recebidos (dívidas com terceiros)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emprestimos_recebidos (
            id SERIAL PRIMARY KEY,
            credor TEXT NOT NULL,
            valor_total REAL NOT NULL,
            taxa_juros REAL DEFAULT 0,
            parcela_mensal REAL NOT NULL,
            data_inicio TEXT,
            data_quitacao_prevista TEXT,
            observacoes TEXT,
            data_criacao TEXT
        )
    ''')

    # Tabela de Contas (bancos e caixas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            saldo_inicial REAL DEFAULT 0,
            data_criacao TEXT
        )
    ''')

    # Tabela de Categorias
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categorias (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            data_criacao TEXT
        )
    ''')

    # Migrations seguras
    for table, col, default in [
        ('transacoes', 'status', 'pendente'),
        ('emprestimos_recebidos', 'status', 'pendente'),
    ]:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS status TEXT DEFAULT '{default}'")
        except Exception:
            conn.rollback()
    for col in ['conta_id', 'data_baixa', 'grupo_recorrencia']:
        try:
            cursor.execute(f"ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS {col} TEXT")
        except Exception:
            conn.rollback()
    for col_def in ['parcela_num INTEGER DEFAULT 1', 'parcela_total INTEGER DEFAULT 1']:
        col = col_def.split()[0]
        try:
            cursor.execute(f"ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS {col_def}")
        except Exception:
            conn.rollback()
    try:
        cursor.execute("ALTER TABLE perfil ADD COLUMN IF NOT EXISTS logo_base64 TEXT")
    except Exception:
        conn.rollback()
    try:
        cursor.execute("ALTER TABLE perfil ADD COLUMN IF NOT EXISTS nome_sistema TEXT DEFAULT 'Tchê Energia'")
    except Exception:
        conn.rollback()
    # Migration: colunas que podem faltar em bancos criados por versões anteriores
    migrations = [
        "ALTER TABLE contas ADD COLUMN IF NOT EXISTS saldo_inicial REAL DEFAULT 0",
        "ALTER TABLE contas ADD COLUMN IF NOT EXISTS data_criacao TEXT",
        "ALTER TABLE emprestimos ADD COLUMN IF NOT EXISTS grupo_recorrencia TEXT",
        "ALTER TABLE emprestimos ADD COLUMN IF NOT EXISTS parcela_num INTEGER DEFAULT 1",
        "ALTER TABLE emprestimos ADD COLUMN IF NOT EXISTS parcela_total INTEGER DEFAULT 1",
        "ALTER TABLE emprestimos_recebidos ADD COLUMN IF NOT EXISTS grupo_recorrencia TEXT",
        "ALTER TABLE emprestimos_recebidos ADD COLUMN IF NOT EXISTS parcela_num INTEGER DEFAULT 1",
        "ALTER TABLE emprestimos_recebidos ADD COLUMN IF NOT EXISTS parcela_total INTEGER DEFAULT 1",
        "ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS categoria TEXT",
        "ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS recorrente INTEGER DEFAULT 0",
        "ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS meses_recorrencia INTEGER DEFAULT 0",
        "ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS hora TEXT",
        "ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS observacoes TEXT",
        "ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS data_vencimento TEXT",
    ]
    for sql in migrations:
        try:
            cursor.execute(sql)
        except Exception:
            conn.rollback()

    # Inserir categorias padrão se a tabela estiver vazia
    cursor.execute('SELECT COUNT(*) FROM categorias')
    if cursor.fetchone()[0] == 0:
        categorias_padrao = [
            ('Salário', 'receita'), ('Freelance / Autônomo', 'receita'), ('Bônus / Comissão', 'receita'),
            ('Investimento / Rendimento', 'receita'), ('Venda de Produto', 'receita'),
            ('Aluguel Recebido', 'receita'), ('Presente / Doação', 'receita'),
            ('Alimentação', 'despesa'), ('Transporte', 'despesa'), ('Moradia / Aluguel', 'despesa'),
            ('Saúde / Farmácia', 'despesa'), ('Educação', 'despesa'), ('Lazer / Entretenimento', 'despesa'),
            ('Assinaturas / Streaming', 'despesa'), ('Vestuário', 'despesa'), ('Serviços / Contas', 'despesa'),
            ('Outro', 'ambos'),
        ]
        for nome, tipo in categorias_padrao:
            cursor.execute('INSERT INTO categorias (nome, tipo, data_criacao) VALUES (%s, %s, %s)',
                           (nome, tipo, datetime.now().isoformat()))

    conn.commit()
    conn.close()

# ======================== FUNÇÕES DO BANCO ========================

def get_perfil():
    """Obter configurações do perfil"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT renda_mensal FROM perfil WHERE id = 1')
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def set_perfil(renda_mensal):
    """Atualizar renda mensal"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM perfil WHERE id = 1')
    cursor.execute('INSERT INTO perfil (id, renda_mensal, data_atualizacao) VALUES (1, %s, %s)',
                   (renda_mensal, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def add_gasto_essencial(nome, valor):
    """Adicionar gasto essencial"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO gastos_essenciais (nome, valor, data_criacao) VALUES (%s, %s, %s)',
                   (nome, valor, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_gastos_essenciais():
    """Obter todos os gastos essenciais"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nome, valor FROM gastos_essenciais ORDER BY id DESC')
    items = cursor.fetchall()
    conn.close()
    return items

def delete_gasto_essencial(id):
    """Deletar gasto essencial"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM gastos_essenciais WHERE id = %s', (id,))
    conn.commit()
    conn.close()

def add_divida(nome, valor_total, taxa_juros, parcela_mensal):
    """Adicionar dívida"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO dividas (nome, valor_total, taxa_juros, parcela_mensal, data_criacao)
                      VALUES (%s, %s, %s, %s, %s)''',
                   (nome, valor_total, taxa_juros, parcela_mensal, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_dividas():
    """Obter todas as dívidas ativas"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, valor_total, taxa_juros, parcela_mensal FROM dividas WHERE status = 'ativa' ORDER BY id DESC")
    items = cursor.fetchall()
    conn.close()
    return items

def delete_divida(id):
    """Deletar dívida"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM dividas WHERE id = %s', (id,))
    conn.commit()
    conn.close()

def add_gasto_variavel(nome, valor):
    """Adicionar gasto variável"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO gastos_variaveis (nome, valor, data_criacao) VALUES (%s, %s, %s)',
                   (nome, valor, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_gastos_variaveis():
    """Obter todos os gastos variáveis"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nome, valor FROM gastos_variaveis ORDER BY id DESC')
    items = cursor.fetchall()
    conn.close()
    return items

def delete_gasto_variavel(id):
    """Deletar gasto variável"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM gastos_variaveis WHERE id = %s', (id,))
    conn.commit()
    conn.close()

def add_transacao(tipo, categoria, descricao, valor, data, data_vencimento='', observacoes='', recorrente=False, meses=0, status='pendente', conta_id=None):
    """Adicionar transação. Se recorrente, cria um registro por parcela."""
    conn = get_conn()
    cursor = conn.cursor()
    hora = datetime.now().strftime('%H:%M:%S')
    total_parcelas = meses if recorrente and meses > 0 else 1
    grupo_id = str(uuid.uuid4()) if recorrente and meses > 0 else None

    try:
        base_date = datetime.strptime(data, '%Y-%m-%d')
    except Exception:
        base_date = datetime.now()

    for i in range(total_parcelas):
        # Calcula data desta parcela (avança i meses)
        month = base_date.month - 1 + i
        year  = base_date.year + month // 12
        month = month % 12 + 1
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(base_date.day, max_day)
        parcela_data = f'{year:04d}-{month:02d}-{day:02d}'

        # Vencimento também avança junto
        parcela_venc = None
        if data_vencimento:
            try:
                base_venc = datetime.strptime(data_vencimento, '%Y-%m-%d')
                vm = base_venc.month - 1 + i
                vy = base_venc.year + vm // 12
                vm = vm % 12 + 1
                vd = min(base_venc.day, calendar.monthrange(vy, vm)[1])
                parcela_venc = f'{vy:04d}-{vm:02d}-{vd:02d}'
            except Exception:
                pass

        cursor.execute('''INSERT INTO transacoes
            (tipo, categoria, descricao, valor, data, data_vencimento, recorrente, meses_recorrencia,
             hora, observacoes, status, conta_id, grupo_recorrencia, parcela_num, parcela_total)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (tipo, categoria, descricao, valor, parcela_data,
             parcela_venc, 1 if recorrente else 0, total_parcelas,
             hora, observacoes, status, conta_id, grupo_id, i + 1, total_parcelas))

    conn.commit()
    conn.close()


def update_transacoes_grupo(grupo_id, excluir_id, tipo, categoria, descricao, valor, observacoes, conta_id):
    """Atualiza campos comuns de todas as parcelas do grupo (exceto data e status de cada uma)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''UPDATE transacoes SET tipo=%s, categoria=%s, descricao=%s, valor=%s,
                      observacoes=%s, conta_id=%s
                      WHERE grupo_recorrencia=%s''',
                   (tipo, categoria, descricao, valor, observacoes, conta_id, grupo_id))
    conn.commit()
    conn.close()

def get_transacoes(data_inicio=None, data_fim=None):
    """Obter transações em um período"""
    conn = get_conn()
    cursor = conn.cursor()

    if data_inicio and data_fim:
        cursor.execute('''SELECT id, tipo, categoria, descricao, valor, data, data_vencimento, recorrente, meses_recorrencia, hora, observacoes, status, conta_id, data_baixa, grupo_recorrencia, parcela_num, parcela_total
                          FROM transacoes WHERE data BETWEEN %s AND %s ORDER BY data DESC, hora DESC''',
                       (data_inicio, data_fim))
    else:
        cursor.execute('SELECT id, tipo, categoria, descricao, valor, data, data_vencimento, recorrente, meses_recorrencia, hora, observacoes, status, conta_id, data_baixa, grupo_recorrencia, parcela_num, parcela_total FROM transacoes ORDER BY data DESC, hora DESC')

    items = cursor.fetchall()
    conn.close()
    return items

def get_transacoes_recorrentes():
    """Obter apenas transações recorrentes"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''SELECT id, tipo, categoria, descricao, valor, data, meses_recorrencia
                      FROM transacoes WHERE recorrente = 1 ORDER BY data DESC''')
    items = cursor.fetchall()
    conn.close()
    return items

def update_transacao(id, tipo, categoria, descricao, valor, data, data_vencimento='', observacoes='', recorrente=False, meses=0, status='pendente', conta_id=None, data_baixa=None):
    conn = get_conn()
    cursor = conn.cursor()
    if status == 'pago' and data_baixa is None:
        data_baixa = datetime.now().strftime('%Y-%m-%d')
    elif status != 'pago':
        data_baixa = None
    cursor.execute('''UPDATE transacoes SET tipo=%s, categoria=%s, descricao=%s, valor=%s, data=%s,
                      data_vencimento=%s, observacoes=%s, recorrente=%s, meses_recorrencia=%s, status=%s, conta_id=%s, data_baixa=%s WHERE id=%s''',
                   (tipo, categoria, descricao, valor, data,
                    data_vencimento if data_vencimento else None,
                    observacoes, 1 if recorrente else 0, meses if recorrente else 0, status, conta_id, data_baixa, id))
    conn.commit()
    conn.close()

def update_status_transacao(id, status):
    conn = get_conn()
    cursor = conn.cursor()
    data_baixa = datetime.now().strftime('%Y-%m-%d') if status == 'pago' else None
    cursor.execute('UPDATE transacoes SET status=%s, data_baixa=%s WHERE id=%s', (status, data_baixa, id))
    conn.commit()
    conn.close()

def delete_transacao(id):
    """Deletar transação"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM transacoes WHERE id = %s', (id,))
    conn.commit()
    conn.close()

def add_pagamento(divida_id, valor_pago, observacoes=''):
    """Registrar pagamento de dívida"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO pagamentos (divida_id, valor_pago, data_pagamento, observacoes)
                      VALUES (%s, %s, %s, %s)''',
                   (divida_id, valor_pago, datetime.now().isoformat(), observacoes))
    conn.commit()
    conn.close()

def get_pagamentos(divida_id):
    """Obter pagamentos de uma dívida"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''SELECT valor_pago, data_pagamento, observacoes FROM pagamentos WHERE divida_id = %s ORDER BY data_pagamento DESC''',
                   (divida_id,))
    items = cursor.fetchall()
    conn.close()
    return items

def add_receita(nome, valor):
    """Adicionar receita adicional"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO receitas (nome, valor, data_criacao) VALUES (%s, %s, %s)',
                   (nome, valor, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_receitas():
    """Obter todas as receitas adicionais"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nome, valor FROM receitas ORDER BY id DESC')
    items = cursor.fetchall()
    conn.close()
    return items

def delete_receita(id):
    """Deletar receita adicional"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM receitas WHERE id = %s', (id,))
    conn.commit()
    conn.close()

def add_emprestimo(nome, valor, data_emprestimo, data_devolucao_esperada, observacoes=''):
    """Adicionar empréstimo pessoal"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO emprestimos (nome, valor, data_emprestimo, data_devolucao_esperada, observacoes, data_criacao)
                      VALUES (%s, %s, %s, %s, %s, %s)''',
                   (nome, valor, data_emprestimo, data_devolucao_esperada, observacoes, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_emprestimos():
    """Obter todos os empréstimos pessoais"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nome, valor, data_emprestimo, data_devolucao_esperada, observacoes FROM emprestimos ORDER BY data_devolucao_esperada ASC')
    items = cursor.fetchall()
    conn.close()
    return items

def delete_emprestimo(id):
    """Deletar empréstimo pessoal"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM emprestimos WHERE id = %s', (id,))
    conn.commit()
    conn.close()

def add_emprestimo_recebido(credor, valor_total, taxa_juros, parcela_mensal, data_inicio, data_quitacao_prevista, observacoes='', status='pendente'):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO emprestimos_recebidos
        (credor, valor_total, taxa_juros, parcela_mensal, data_inicio, data_quitacao_prevista, observacoes, data_criacao, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
        (credor, valor_total, taxa_juros, parcela_mensal, data_inicio, data_quitacao_prevista, observacoes, datetime.now().isoformat(), status))
    conn.commit()
    conn.close()

def get_emprestimos_recebidos():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id, credor, valor_total, taxa_juros, parcela_mensal, data_inicio, data_quitacao_prevista, observacoes, status FROM emprestimos_recebidos ORDER BY data_criacao DESC')
    items = cursor.fetchall()
    conn.close()
    return items

def update_emprestimo_recebido(id, credor, valor_total, taxa_juros, parcela_mensal, data_inicio, data_quitacao_prevista, observacoes='', status='pendente'):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''UPDATE emprestimos_recebidos SET credor=%s, valor_total=%s, taxa_juros=%s,
        parcela_mensal=%s, data_inicio=%s, data_quitacao_prevista=%s, observacoes=%s, status=%s WHERE id=%s''',
        (credor, valor_total, taxa_juros, parcela_mensal, data_inicio, data_quitacao_prevista, observacoes, status, id))
    conn.commit()
    conn.close()

def update_status_emprestimo(id, status):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE emprestimos_recebidos SET status=%s WHERE id=%s', (status, id))
    conn.commit()
    conn.close()

def delete_emprestimo_recebido(id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM emprestimos_recebidos WHERE id = %s', (id,))
    conn.commit()
    conn.close()

def add_categoria(nome, tipo):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO categorias (nome, tipo, data_criacao) VALUES (%s, %s, %s)',
                   (nome, tipo, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_categorias():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nome, tipo FROM categorias ORDER BY tipo, nome')
    items = cursor.fetchall()
    conn.close()
    return items

def update_categoria(id, nome, tipo):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE categorias SET nome = %s, tipo = %s WHERE id = %s', (nome, tipo, id))
    conn.commit()
    conn.close()

def delete_categoria(id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM categorias WHERE id = %s', (id,))
    conn.commit()
    conn.close()

# ======================== ANÁLISE DE EMPRÉSTIMO ========================

def analisar_emprestimo():
    """
    Análise inteligente sobre quando buscar empréstimo consolidado.
    Recomenda APENAS se não houver outra opção.
    """
    renda = get_perfil()
    gastos_essenciais = get_gastos_essenciais()
    dividas = get_dividas()
    gastos_variaveis = get_gastos_variaveis()

    if not renda or not dividas:
        return {
            'recomenda_emprestimo': False,
            'urgencia': 'nenhuma',
            'motivo': 'Dados insuficientes',
            'valor_sugerido': 0,
            'economia_potencial': 0,
            'alternativas': []
        }

    # Cálculos
    diezmo = renda * 0.1
    saldo_apos_diezmo = renda - diezmo

    total_essenciais = sum(item[2] for item in gastos_essenciais)
    total_variaveis = sum(item[2] for item in gastos_variaveis)

    total_dividas = sum(d[2] for d in dividas)
    total_parcelas = sum(d[4] for d in dividas)

    # Ordenar dívidas por taxa de juros (maior primeiro)
    dividas_sorted = sorted(dividas, key=lambda x: x[3], reverse=True)

    # Indicadores
    saldo_mensal = saldo_apos_diezmo - total_essenciais - total_variaveis
    rendaAnual = renda * 12
    index_renda = (total_dividas / rendaAnual * 100) if rendaAnual > 0 else 0
    index_parcelas = (total_parcelas / renda * 100) if renda > 0 else 0

    juros_mensal_total = sum(d[2] * d[4] / 100 for d in dividas)
    taxa_media_juros = (sum(d[3] * d[2] for d in dividas) / total_dividas) if total_dividas > 0 else 0

    # Análise de alternativas
    alternativas = []
    recomenda_emprestimo = False
    urgencia = 'nenhuma'
    valor_sugerido = 0
    economia_potencial = 0

    # 1. VERIFICAR GASTOS VARIÁVEIS
    if total_variaveis > 0:
        corte_possivel = total_variaveis * 0.7  # Cortar 70% dos variáveis
        alternativas.append({
            'alternativa': 'Cortar gastos variáveis',
            'economia': corte_possivel,
            'viavel': True,
            'descricao': f'Reduzir streaming, cafés e compras em 70% = R$ {corte_possivel:.2f}'
        })

    # 2. RENEGOCIAR TAXAS (se houver juros altos)
    if taxa_media_juros > 5:
        economia_reducao_taxa = total_dividas * (taxa_media_juros - 3) / 100 * 12
        alternativas.append({
            'alternativa': 'Renegociar taxas com credores',
            'economia': economia_reducao_taxa,
            'viavel': True,
            'descricao': f'Negociar redução de {taxa_media_juros:.1f}% para 3% = R$ {economia_reducao_taxa:.2f}/ano'
        })

    # 3. AUMENTAR RENDA
    alternativas.append({
        'alternativa': 'Buscar renda extra',
        'economia': 500,  # Valor estimado
        'viavel': True,
        'descricao': 'Freelance, trabalho extra = R$ 500+/mês'
    })

    # DECISÃO DE EMPRÉSTIMO (ÚLTIMO RECURSO)
    if index_renda > 80 or index_parcelas > 40 or (saldo_mensal < 0 and taxa_media_juros > 8):
        recomenda_emprestimo = True

        if saldo_mensal < 0:
            urgencia = 'CRÍTICA'
        elif index_parcelas > 40:
            urgencia = 'ALTA'
        else:
            urgencia = 'MÉDIA'

        # Calcular valor ideal do empréstimo
        valor_consolidacao_total = total_dividas

        dividas_altos_juros = [d for d in dividas if d[3] > 5]
        valor_altos_juros = sum(d[2] for d in dividas_altos_juros)

        taxa_emprestimo_estimada = 1.0  # 1% a.m. é conservador

        juros_atuais_altos = sum(d[2] * d[3] / 100 for d in dividas_altos_juros)
        juros_novo_altos = valor_altos_juros * taxa_emprestimo_estimada / 100
        economia_altos = (juros_atuais_altos - juros_novo_altos) * 30  # 30 dias

        valor_sugerido = valor_altos_juros if economia_altos > 50 else 0
        economia_potencial = max(0, economia_altos * 12)  # Anualizado

    return {
        'recomenda_emprestimo': recomenda_emprestimo,
        'urgencia': urgencia,
        'motivo': _gerar_motivo_emprestimo(index_renda, index_parcelas, saldo_mensal, taxa_media_juros),
        'valor_sugerido': valor_sugerido,
        'economia_potencial': economia_potencial,
        'alternativas': alternativas,
        'indicadores': {
            'endividamento_porcento': round(index_renda, 1),
            'parcelas_porcento': round(index_parcelas, 1),
            'saldo_mensal': round(saldo_mensal, 2),
            'taxa_media_juros': round(taxa_media_juros, 2),
            'juros_mensais': round(juros_mensal_total, 2)
        }
    }

def _gerar_motivo_emprestimo(index_renda, index_parcelas, saldo_mensal, taxa_media):
    """Gerar motivo legível para a recomendação"""
    razoes = []

    if index_renda > 80:
        razoes.append(f'Endividamento de {index_renda:.0f}% (crítico)')

    if index_parcelas > 40:
        razoes.append(f'{index_parcelas:.0f}% da renda vai para parcelas')

    if saldo_mensal < 0:
        razoes.append(f'Saldo mensal negativo de R$ {abs(saldo_mensal):.2f}')

    if taxa_media > 8:
        razoes.append(f'Taxa média de {taxa_media:.1f}% a.m.')

    return ' + '.join(razoes) if razoes else 'Situação crítica'

# ======================== ROTAS ========================

@app.route('/')
def index():
    """Página principal"""
    return render_template('gestor_financeiro.html')

# API - Perfil
@app.route('/api/perfil', methods=['GET', 'POST'])
def api_perfil():
    if request.method == 'POST':
        data = request.json
        set_perfil(data.get('renda_mensal', 0))
        return jsonify({'success': True})
    else:
        renda = get_perfil()
        return jsonify({'renda_mensal': renda})

@app.route('/api/logo', methods=['GET', 'POST'])
def api_logo():
    conn = get_conn()
    cursor = conn.cursor()
    if request.method == 'POST':
        data = request.json
        logo_base64 = data.get('logo_base64', '')
        nome_sistema = data.get('nome_sistema', 'Tchê Energia')
        cursor.execute('SELECT id FROM perfil WHERE id = 1')
        if cursor.fetchone():
            cursor.execute('UPDATE perfil SET logo_base64=%s, nome_sistema=%s WHERE id=1',
                           (logo_base64, nome_sistema))
        else:
            cursor.execute('INSERT INTO perfil (id, renda_mensal, logo_base64, nome_sistema, data_atualizacao) VALUES (1, 0, %s, %s, %s)',
                           (logo_base64, nome_sistema, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    else:
        cursor.execute('SELECT logo_base64, nome_sistema FROM perfil WHERE id = 1')
        row = cursor.fetchone()
        conn.close()
        return jsonify({
            'logo_base64': row[0] if row else '',
            'nome_sistema': row[1] if row and row[1] else 'Tchê Energia'
        })

# API - Gastos Essenciais
@app.route('/api/gastos-essenciais', methods=['GET', 'POST', 'DELETE'])
def api_gastos_essenciais():
    if request.method == 'POST':
        data = request.json
        add_gasto_essencial(data['nome'], data['valor'])
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        data = request.json
        delete_gasto_essencial(data['id'])
        return jsonify({'success': True})
    else:
        items = get_gastos_essenciais()
        return jsonify([{'id': i[0], 'nome': i[1], 'valor': i[2]} for i in items])

# API - Dívidas
@app.route('/api/dividas', methods=['GET', 'POST', 'DELETE'])
def api_dividas():
    if request.method == 'POST':
        data = request.json
        add_divida(data['nome'], data['valor_total'], data['taxa_juros'], data['parcela_mensal'])
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        data = request.json
        delete_divida(data['id'])
        return jsonify({'success': True})
    else:
        items = get_dividas()
        return jsonify([{'id': i[0], 'nome': i[1], 'valor_total': i[2], 'taxa_juros': i[3], 'parcela_mensal': i[4]} for i in items])

# API - Gastos Variáveis
@app.route('/api/gastos-variaveis', methods=['GET', 'POST', 'DELETE'])
def api_gastos_variaveis():
    if request.method == 'POST':
        data = request.json
        add_gasto_variavel(data['nome'], data['valor'])
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        data = request.json
        delete_gasto_variavel(data['id'])
        return jsonify({'success': True})
    else:
        items = get_gastos_variaveis()
        return jsonify([{'id': i[0], 'nome': i[1], 'valor': i[2]} for i in items])

# API - Transações
@app.route('/api/transacoes', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def api_transacoes():
    if request.method == 'POST':
        data = request.json
        add_transacao(data['tipo'], data['categoria'], data.get('descricao', ''),
                     data['valor'], data['data'], data.get('dataVencimento', ''),
                     data.get('observacoes', ''), data.get('recorrente', False), data.get('meses', 0),
                     data.get('status', 'pendente'), data.get('conta_id'))
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json
        escopo = data.get('escopo', 'parcela')  # 'parcela' ou 'grupo'
        if escopo == 'grupo' and data.get('grupo_recorrencia'):
            update_transacoes_grupo(data['grupo_recorrencia'], data['id'],
                                    data['tipo'], data['categoria'], data.get('descricao', ''),
                                    data['valor'], data.get('observacoes', ''), data.get('conta_id'))
        else:
            update_transacao(data['id'], data['tipo'], data['categoria'], data.get('descricao', ''),
                            data['valor'], data['data'], data.get('dataVencimento', ''),
                            data.get('observacoes', ''), data.get('recorrente', False), data.get('meses', 0),
                            data.get('status', 'pendente'), data.get('conta_id'), data.get('data_baixa'))
        return jsonify({'success': True})
    elif request.method == 'PATCH':
        data = request.json
        update_status_transacao(data['id'], data['status'])
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        data = request.json
        escopo = data.get('escopo', 'parcela')
        if escopo == 'grupo' and data.get('grupo_recorrencia'):
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM transacoes WHERE grupo_recorrencia=%s', (data['grupo_recorrencia'],))
            conn.commit()
            conn.close()
        else:
            delete_transacao(data['id'])
        return jsonify({'success': True})
    else:
        data_inicio = request.args.get('inicio')
        data_fim = request.args.get('fim')
        items = get_transacoes(data_inicio, data_fim)
        return jsonify([{'id': i[0], 'tipo': i[1], 'categoria': i[2], 'descricao': i[3],
                        'valor': i[4], 'data': i[5], 'dataVencimento': i[6], 'recorrente': i[7],
                        'mesesRecorrencia': i[8], 'hora': i[9], 'observacoes': i[10],
                        'status': i[11] or 'pendente', 'conta_id': i[12], 'data_baixa': i[13],
                        'grupo_recorrencia': i[14], 'parcela_num': i[15], 'parcela_total': i[16]} for i in items])

# API - Transações Recorrentes
@app.route('/api/transacoes-recorrentes', methods=['GET'])
def api_transacoes_recorrentes():
    items = get_transacoes_recorrentes()
    return jsonify([{'id': i[0], 'tipo': i[1], 'categoria': i[2], 'descricao': i[3],
                    'valor': i[4], 'data': i[5], 'mesesRecorrencia': i[6]} for i in items])

# API - Pagamentos
@app.route('/api/pagamentos/<int:divida_id>', methods=['GET', 'POST'])
def api_pagamentos(divida_id):
    if request.method == 'POST':
        data = request.json
        add_pagamento(divida_id, data['valor_pago'], data.get('observacoes', ''))
        return jsonify({'success': True})
    else:
        items = get_pagamentos(divida_id)
        return jsonify([{'valor_pago': i[0], 'data_pagamento': i[1], 'observacoes': i[2]} for i in items])

# API - Receitas
@app.route('/api/receitas', methods=['GET', 'POST', 'DELETE'])
def api_receitas():
    if request.method == 'POST':
        data = request.json
        add_receita(data['nome'], data['valor'])
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        data = request.json
        delete_receita(data['id'])
        return jsonify({'success': True})
    else:
        items = get_receitas()
        return jsonify([{'id': i[0], 'nome': i[1], 'valor': i[2]} for i in items])

# API - Empréstimos
@app.route('/api/emprestimos', methods=['GET', 'POST', 'DELETE'])
def api_emprestimos():
    if request.method == 'POST':
        data = request.json
        add_emprestimo(data['nome'], data['valor'], data['data_emprestimo'],
                      data['data_devolucao_esperada'], data.get('observacoes', ''))
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        data = request.json
        delete_emprestimo(data['id'])
        return jsonify({'success': True})
    else:
        items = get_emprestimos()
        return jsonify([{'id': i[0], 'nome': i[1], 'valor': i[2], 'data_emprestimo': i[3],
                        'data_devolucao_esperada': i[4], 'observacoes': i[5]} for i in items])

# API - Empréstimos Recebidos
@app.route('/api/emprestimos-recebidos', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def api_emprestimos_recebidos():
    if request.method == 'POST':
        d = request.json
        add_emprestimo_recebido(d['credor'], d['valor_total'], d.get('taxa_juros', 0),
                                d['parcela_mensal'], d.get('data_inicio', ''),
                                d.get('data_quitacao_prevista', ''), d.get('observacoes', ''),
                                d.get('status', 'pendente'))
        return jsonify({'success': True})
    elif request.method == 'PUT':
        d = request.json
        update_emprestimo_recebido(d['id'], d['credor'], d['valor_total'], d.get('taxa_juros', 0),
                                   d['parcela_mensal'], d.get('data_inicio', ''),
                                   d.get('data_quitacao_prevista', ''), d.get('observacoes', ''),
                                   d.get('status', 'pendente'))
        return jsonify({'success': True})
    elif request.method == 'PATCH':
        d = request.json
        update_status_emprestimo(d['id'], d['status'])
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        delete_emprestimo_recebido(request.json['id'])
        return jsonify({'success': True})
    else:
        items = get_emprestimos_recebidos()
        return jsonify([{'id': i[0], 'credor': i[1], 'valor_total': i[2], 'taxa_juros': i[3],
                         'parcela_mensal': i[4], 'data_inicio': i[5],
                         'data_quitacao_prevista': i[6], 'observacoes': i[7],
                         'status': i[8] or 'pendente'} for i in items])

# API - Contas
def add_conta(nome, tipo, saldo_inicial=0):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO contas (nome, tipo, saldo_inicial, data_criacao) VALUES (%s, %s, %s, %s)',
                   (nome, tipo, saldo_inicial, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_contas():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nome, tipo, saldo_inicial FROM contas ORDER BY tipo, nome')
    items = cursor.fetchall()
    conn.close()
    return items

def update_conta(id, nome, tipo, saldo_inicial=0):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE contas SET nome=%s, tipo=%s, saldo_inicial=%s WHERE id=%s', (nome, tipo, saldo_inicial, id))
    conn.commit()
    conn.close()

def delete_conta(id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM contas WHERE id=%s', (id,))
    conn.commit()
    conn.close()

@app.route('/api/contas', methods=['GET', 'POST', 'PUT', 'DELETE'])
def api_contas():
    if request.method == 'POST':
        d = request.json
        add_conta(d['nome'], d['tipo'], d.get('saldo_inicial', 0))
        return jsonify({'success': True})
    elif request.method == 'PUT':
        d = request.json
        update_conta(d['id'], d['nome'], d['tipo'], d.get('saldo_inicial', 0))
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        delete_conta(request.json['id'])
        return jsonify({'success': True})
    else:
        items = get_contas()
        conn = get_conn()
        cursor = conn.cursor()
        result = []
        for i in items:
            cursor.execute("SELECT COALESCE(SUM(valor),0) FROM transacoes WHERE conta_id=%s AND tipo='receita'", (str(i[0]),))
            rec = cursor.fetchone()[0]
            cursor.execute("SELECT COALESCE(SUM(valor),0) FROM transacoes WHERE conta_id=%s AND tipo='despesa' AND status='pago'", (str(i[0]),))
            desp = cursor.fetchone()[0]
            saldo_atual = i[3] + rec - desp
            result.append({'id': i[0], 'nome': i[1], 'tipo': i[2], 'saldo_inicial': i[3], 'saldo_atual': saldo_atual})
        conn.close()
        return jsonify(result)

@app.route('/api/categorias', methods=['GET', 'POST', 'PUT', 'DELETE'])
def api_categorias():
    if request.method == 'POST':
        data = request.json
        add_categoria(data['nome'], data['tipo'])
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json
        update_categoria(data['id'], data['nome'], data['tipo'])
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        data = request.json
        delete_categoria(data['id'])
        return jsonify({'success': True})
    else:
        items = get_categorias()
        return jsonify([{'id': i[0], 'nome': i[1], 'tipo': i[2]} for i in items])

# API - Análise de Empréstimo
@app.route('/api/analise-emprestimo', methods=['GET'])
def api_analise_emprestimo():
    analise = analisar_emprestimo()
    return jsonify(analise)

# Rota de diagnóstico — acesse /api/debug para ver o erro real
@app.route('/api/debug')
def api_debug():
    import traceback
    result = {'DATABASE_URL_set': bool(os.environ.get('DATABASE_URL')), 'db_ok': False, 'error': None, 'tables': []}
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        result['tables'] = [r[0] for r in cur.fetchall()]
        result['db_ok'] = True
        conn.close()
    except Exception as e:
        result['error'] = traceback.format_exc()
    return jsonify(result)

# Handler global de erros — retorna JSON em vez de HTML
@app.errorhandler(500)
def handle_500(e):
    import traceback
    return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

# Inicializa o banco sempre que o módulo for carregado (Vercel + local)
_init_error = None
try:
    init_db()
except Exception as e:
    import traceback
    _init_error = traceback.format_exc()
    print(f"[WARN] init_db falhou: {_init_error}")

if __name__ == '__main__':
    app.run(debug=False)
