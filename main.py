from langchain_ollama import OllamaLLM
from langchain.prompts import ChatPromptTemplate
import json

# Carregar os produtos de um JSON externo (opcional)
with open("produtos.json", "r", encoding="utf-8") as f:
    produtos = json.load(f)

# Modelo
model = OllamaLLM(model="qwen3:1.7b")

# Template do prompt
template = """
Você é um assistente especializado em ajudar na gestão de um mercadinho de bairro que fala apenas português do Brasil.  
Responda de forma objetiva e direta.
Não invente produtos nem misture os nomes.Só use informações reais do catálogo.
Você receberá uma lista de produtos em formato JSON.  
Você retornará os itens escritos em texto e não todas as informações.
Você retornará as informações completas somente se for pedido.

Cada produto possui os seguintes campos:
- nome
- descrição
- marca
- preço
- data_validade (YYYY-MM-DD)
- código
- categoria

Aqui estão os produtos disponíveis:
{produtos}

Suas tarefas:
1. Responder perguntas sobre o estoque (ex: quais produtos vencem hoje ou daqui a X dias, quais são os mais baratos, qual o preço do produto informado etc.).  
2. Quando listar produtos, responda sempre texto.
3. Listar produtos com informações detalhas JSON apenas se for pedido.  
3. Se receber uma lista bagunçada, organize-a e devolva agrupada por categorias.  
4. Seja claro e direto nas respostas, sem inventar informações fora da lista.  

Aqui está a pergunta do usuário:
{pergunta}
"""

def adicionar_produto(produto):
    global produtos
    produtos.append(produto)
    with open("produtos.json", "w", encoding="utf-8") as f:
        json.dump(produtos, f, ensure_ascii=False, indent=2)
    print(f"✅ Produto '{produto['nome']}' adicionado com sucesso ao estoque!")



# Criação do prompt e da chain
prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model

# Loop principal
while True:
    
    print("\n\n-------------------------------")
    print("""Sugestões:
          - Consultar sobre o estoque ou perguntar sobre os produtos (ex: data de validade, quais são os mais baratos, qual o preço deste produto (nome))
          - Adicionar Itens ao estoque 
          """)
    pergunta = input("Digite sua pergunta (q para sair): ")
    print("\n\n")
    if pergunta.lower() == "q":
        break
    
    # Passar produtos + pergunta para o modelo
    resposta = chain.invoke({"produtos": json.dumps(produtos, ensure_ascii=False, indent=2), 
                           "pergunta": pergunta})
    
    if "<think>" in resposta:
        resposta = resposta.split("</think>")[-1].strip()

    print(resposta)
