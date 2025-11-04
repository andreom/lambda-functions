# Lambda Integration

## 📋 Descrição
Função Lambda que automaticamente processa arquivos CSV do S3 e os envia para o webservice via protocolo SOAP. 
A função monitora um bucket S3, processa arquivos CSV quando são criados e envia notificações por email com o resultado do processamento.

## 🎯 Funcionalidade
- **Trigger**: Criação de arquivos `.csv` em bucket S3 configurado
- **Processamento**: Lê arquivo CSV, codifica em base64 e envia via SOAP
- **Notificação**: Envia emails de sucesso ou erro com detalhes do processamento
- **Organização**: Opcionalmente move arquivos processados para pastas específicas

## ⚙️ Configuração

### Variáveis de Ambiente Obrigatórias

**Nota**: A função valida automaticamente as variáveis obrigatórias na inicialização. Se alguma estiver ausente, a função retornará erro 500 com mensagem detalhada.

#### Webservice SAUDI/VOXIS
```bash
WS_URL=https://exemplo.domain.com.br/webservice/transmiteArquivoService    # URL do webservice SOAP
WS_LOGIN=usuario_webservice                                               # Login para autenticação
WS_PASSWORD=senha_webservice                                              # Senha para autenticação
CLIENT_CODE=codigo_cliente                                                # Código do cliente no sistema
SERVICE_ID=BNFC                                                          # ID do serviço (ex: BNFC)
```

#### Configurações de Email
```bash
EMAIL_SENDER=no-reply@empresa.com.br                                     # Email remetente (verificado no SES)
EMAIL_RECIPIENTS=admin@empresa.com.br,equipe@empresa.com.br               # Emails destinatários (separados por vírgula)
EMAIL_CC=supervisor@empresa.com.br                                       # Emails em cópia (opcional)
```

### Variáveis de Ambiente Opcionais
```bash
FILE_TYPE=CSV                                                            # Tipo de arquivo (padrão: CSV)
WS_TIMEOUT=550                                                           # Timeout em segundos (padrão: 550)
VERIFY_SSL=1                                                             # Verificar SSL (1=sim, 0=não)

# Organização de arquivos
MOVE_PROCESSED=true                                                      # Mover arquivos processados (true/false)
PROCESSED_PATH=processados/                                              # Pasta para arquivos processados
DELETE_ORIGINAL=true                                                     # Deletar arquivo original após mover (true/false)
MOVE_FAILED=true                                                         # Mover arquivos com erro (true/false)
ERROR_PATH=erros/                                                        # Pasta para arquivos com erro
```

## 🔐 Permissões IAM Necessárias

### Para a Role da Lambda
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:CopyObject"
            ],
            "Resource": [
                "arn:aws:s3:::seu-bucket-origem/*",
                "arn:aws:s3:::seu-bucket-destino/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "ses:SendEmail",
                "ses:SendRawEmail"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        }
    ]
}
```

## 🔄 Resiliência e Retry
A função implementa retry automático com backoff exponencial para operações críticas:
- **Envio de emails**: até 3 tentativas com delays de 1s, 2s, 4s
- **Backoff exponencial**: reduz chances de falhas transientes
- **Logs detalhados**: registra cada tentativa de retry
- **Parse de resposta**: dupla estratégia (XML + regex) para máxima confiabilidade

## 📧 Configuração do SES
1. **Verificar emails no AWS SES**:
   - Email remetente (`EMAIL_SENDER`)
   - Emails destinatários (se estiver no sandbox)

2. **Para produção**: Configurar domínio verificado no SES

3. **Mover para produção**: Solicitar saída do sandbox para enviar para qualquer email

## 🚀 Configuração do S3 Trigger
1. **Acesse o bucket S3**
2. **Vá em Properties > Event Notifications**
3. **Crie nova notificação**:
   - **Name**: `lambda-saudi-voxis-trigger`
   - **Prefix**: `uploads/` (se aplicável)
   - **Suffix**: `.csv`
   - **Event Types**: `s3:ObjectCreated:*`
   - **Destination**: Lambda Function > [nome-da-sua-funcao]

## 🔍 Monitoramento

### Logs
- **CloudWatch Logs**: `/aws/lambda/[nome-da-funcao]`
- **Métricas**: Duração, erros, invocações
- **Emails**: Notificações automáticas com detalhes

### Logs Importantes
```bash
# Verificar logs recentes
aws logs filter-log-events --log-group-name /aws/lambda/[nome-da-funcao] --start-time $(date -d '1 hour ago' +%s)000

# Verificar erros
aws logs filter-log-events --log-group-name /aws/lambda/[nome-da-funcao] --filter-pattern "ERROR"
```

## 📝 Formato do Email de Notificação
O sistema envia emails em HTML contendo:
- **Status**: Sucesso ou Erro
- **Protocolo**: Número do protocolo retornado
- **Estatísticas**: Total de registros, aceitos, rejeitados
- **Resposta completa**: Detalhes técnicos da resposta

## 🚀 Deployment

### Passo a Passo
1. **Criar função Lambda**:
   ```bash
   aws lambda create-function \
     --function-name saudi-voxis-integration \
     --runtime python3.9 \
     --role arn:aws:iam::account:role/lambda-role \
     --handler lambda_function.lambda_handler \
     --zip-file fileb://function.zip
   ```

2. **Configurar variáveis de ambiente**:
   ```bash
   aws lambda update-function-configuration \
     --function-name saudi-voxis-integration \
     --environment Variables='{
       "WS_URL":"https://...",
       "WS_LOGIN":"...",
       "WS_PASSWORD":"...",
       "CLIENT_CODE":"...",
       "SERVICE_ID":"...",
       "EMAIL_SENDER":"...",
       "EMAIL_RECIPIENTS":"..."
     }'
   ```

3. **Configurar timeout** (recomendado: 10 minutos):
   ```bash
   aws lambda update-function-configuration \
     --function-name saudi-voxis-integration \
     --timeout 600
   ```

4. **Configurar trigger S3**
5. **Testar com arquivo de exemplo**

## ⚠️ Troubleshooting

### Problemas Comuns
| Problema | Causa Provável | Solução |
|----------|----------------|---------|
| Email não enviado | SES não configurado | Verificar emails no SES |
| Timeout na requisição | WS_TIMEOUT muito baixo | Aumentar timeout |
| Erro de SSL | Certificado inválido | Configurar `VERIFY_SSL=0` (não recomendado para prod) |
| Arquivo não processado | Trigger S3 mal configurado | Verificar configuração do evento |
| Erro de autenticação | Credenciais incorretas | Verificar `WS_LOGIN` e `WS_PASSWORD` |

### Teste Manual
```python
# Evento de teste para a Lambda
{
  "Records": [
    {
      "s3": {
        "bucket": {"name": "seu-bucket"},
        "object": {"key": "arquivo-teste.csv"}
      }
    }
  ]
}
```

---
**Última atualização**: Junho 2025  
**Versão**: 2.0
