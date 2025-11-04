# AWS Lambda Functions

Repositório de funções Lambda para automação de processos AWS com integração S3, SES e webservices SOAP.

## 📁 Estrutura do Projeto

```
lambda-functions/
├── README.md                              # Documentação principal
├── requirements.txt                       # Dependências Python
├── .gitignore                            # Arquivos ignorados pelo Git
├── .env.example                          # Exemplo de variáveis de ambiente
└── buckets_s3/                           # Funções relacionadas a S3
    ├── s3_copy_fail_email.py             # Cópia de arquivos entre buckets com notificação
    ├── README_s3_copy_fail_email.md      # Documentação da função de cópia
    ├── s3_csv_to_api_soap.py             # Integração S3 → SOAP webservice
    └── README_s3_csv_to_api_soap.md      # Documentação da função SOAP
```

## 🚀 Funções Disponíveis

### 1. S3 Copy with Email Notification
**Arquivo:** `buckets_s3/s3_copy_fail_email.py`

Função Lambda para copiar arquivos CSV.GZ entre buckets S3 com notificação de erros por email.

**Características:**
- Trigger automático por eventos S3 (ObjectCreated)
- Cópia inteligente com reorganização de paths
- Notificação de erros via AWS SES
- Retry automático com backoff exponencial
- Validação de variáveis de ambiente

**Variáveis de Ambiente:**
- `SOURCE_BUCKET` - Bucket de origem
- `DESTINATION_BUCKET` - Bucket de destino
- `DESTINATION_PREFIX` - Prefixo do path de destino
- `EMAIL_SOURCE` - Email remetente (SES)
- `EMAIL_DESTINATION` - Email destinatário

[Documentação completa →](buckets_s3/README_s3_copy_fail_email.md)

---

### 2. CSV to SOAP Webservice Integration
**Arquivo:** `buckets_s3/s3_csv_to_api_soap.py`

Função Lambda para processar arquivos CSV do S3 e enviar para webservice SOAP (SAUDI/VOXIS).

**Características:**
- Leitura automática de arquivos CSV do S3
- Encoding base64 de arquivos e credenciais
- Integração SOAP com timeout configurável
- Parse de resposta XML com fallback regex
- Emails HTML formatados com estatísticas detalhadas
- Movimentação automática de arquivos processados
- Retry automático com backoff exponencial
- Validação de variáveis de ambiente

**Variáveis de Ambiente:**
- `WS_URL` - URL do webservice SOAP
- `WS_LOGIN` - Login de autenticação
- `WS_PASSWORD` - Senha de autenticação
- `CLIENT_CODE` - Código do cliente
- `SERVICE_ID` - ID do serviço
- `EMAIL_SENDER` - Email remetente (SES)
- `EMAIL_RECIPIENTS` - Emails destinatários (separados por vírgula)
- `EMAIL_CC` - Emails em cópia (separados por vírgula)

[Documentação completa →](buckets_s3/README_s3_csv_to_api_soap.md)

---

## 🛠️ Configuração

### Pré-requisitos

- Python 3.11+
- AWS CLI configurado
- Credenciais AWS com permissões adequadas
- Conta AWS SES verificada (para envio de emails)

### Instalação de Dependências

```bash
pip install -r requirements.txt
```

### Configuração de Variáveis de Ambiente

Copie o arquivo de exemplo e configure suas variáveis:

```bash
cp .env.example .env
# Edite o arquivo .env com suas configurações
```

## 📦 Deploy

### Deploy Manual

1. **Criar pacote de deployment:**
```bash
zip -r function.zip buckets_s3/s3_copy_fail_email.py
```

2. **Upload para Lambda:**
```bash
aws lambda update-function-code \
  --function-name s3-copy-fail-email \
  --zip-file fileb://function.zip
```

3. **Configurar variáveis de ambiente:**
```bash
aws lambda update-function-configuration \
  --function-name s3-copy-fail-email \
  --environment Variables="{SOURCE_BUCKET=my-bucket,EMAIL_SOURCE=noreply@example.com}"
```

### Deploy com SAM

```bash
sam build
sam deploy --guided
```

## 🔒 Permissões IAM Necessárias

### S3 Copy Function
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:HeadObject"
      ],
      "Resource": "arn:aws:s3:::source-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:HeadObject"
      ],
      "Resource": "arn:aws:s3:::destination-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": "ses:SendEmail",
      "Resource": "*"
    }
  ]
}
```

### SOAP Integration Function
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::your-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": "ses:SendEmail",
      "Resource": "*"
    }
  ]
}
```

## 🧪 Testes

Execute os testes unitários:

```bash
python -m pytest tests/
```

## 📊 Monitoramento

Todas as funções registram logs detalhados no CloudWatch Logs:

- **Log Group:** `/aws/lambda/<function-name>`
- **Métricas:** Duration, Memory, Invocations, Errors

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

## 📝 Convenções

- **Nomenclatura:** snake_case para arquivos e funções
- **Documentação:** Docstrings em português
- **Commits:** Mensagens descritivas em português
- **READMEs:** Um por função Lambda

## 🔄 Versionamento

- **v1.0** - S3 Copy with Email Notification
- **v2.0** - CSV to SOAP Integration

## 📄 Licença

Este projeto é proprietário e confidencial.

## 📧 Contato

Para dúvidas ou suporte, entre em contato com a equipe de desenvolvimento.
