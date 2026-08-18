# Otimizador diário de paletes — Transportadora Mello

Aplicação Streamlit com modelo de programação inteira mista em Python. A
formulação usa Pyomo e é resolvida pelo HiGHS por meio do pacote `highspy`.
Não utiliza AMPL nem solver comercial.

## O que o modelo decide

- quando coletar paletes retidos nos clientes;
- quando devolver paletes disponíveis aos embarcadores;
- qual tipo de veículo e quantas viagens utilizar;
- quando aceitar uma oferta de coleta feita pelo embarcador;
- quando é economicamente melhor deixar um saldo pendente.

## Conceito do vale

O vale não quita a obrigação. Ele representa um lote de paletes físicos
retidos em um cliente, com tipo, quantidade, vencimento inclusivo, antecedência
mínima, custo por dia por palete e custo de perda por palete.

Depois da coleta, o lote entra no estoque da Mello no dia seguinte. A obrigação
perante o embarcador somente diminui quando os paletes chegam ao embarcador ou
são coletados por ele na Mello.

## Premissas da versão inicial

- horizonte em dias corridos;
- coleta parcial de um vale é permitida;
- paletes do mesmo tipo são intercambiáveis entre embarcadores;
- uma viagem atende somente um destino;
- a frota dedicada a paletes é informada por veículo e dia;
- a ameaça de débito é tudo ou nada: qualquer saldo no prazo aciona o valor
  integral;
- não existe obrigação de zerar todos os saldos no fim do horizonte.

## Instalação

Requer Python 3.10 ou superior.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Execução

```powershell
streamlit run app.py
```

Para desenvolvimento e testes:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

A aplicação já inicia com um cenário ilustrativo. Use **Restaurar exemplo**
para recuperar os dados e **Sincronizar calendário e rotas** depois de alterar
o horizonte, os clientes, embarcadores ou veículos.

## Arquivos

- `app.py`: interface Streamlit e exportação para Excel;
- `optimizer.py`: validação, formulação Pyomo, execução do HiGHS e relatórios;
- `sample_data.py`: cenário inicial e sincronização das grades de dados;
- `tests/test_optimizer.py`: testes do modelo e das regras de negócio.

## Interpretação do custo sem agir

O cenário-base mantém os estoques parados durante o horizonte, perde todos os
vales que vencerem e aceita os débitos com prazo dentro do período. A economia
estimada é a diferença entre esse cenário e o plano otimizado.

## Deploy no Streamlit Community Cloud

1. Publique este diretório em um repositório do GitHub.
2. Acesse `https://share.streamlit.io` e escolha **Create app**.
3. Selecione o repositório, a branch `main` e o arquivo `app.py`.
4. Escolha Python 3.12 nas configurações avançadas e confirme o deploy.

O projeto não usa segredos. Caso eles sejam adicionados futuramente, mantenha
`.streamlit/secrets.toml` somente no computador e cadastre os valores pela tela
de configurações do Streamlit Cloud.
