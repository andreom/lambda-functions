# Lambda S3 Copy com Notificação de Email

## 📋 Descrição
Função Lambda que automaticamente copia arquivos CSV.GZ do bucket de relatórios do Snowflake para o bucket de integração, organizando-os em uma estrutura específica de diretórios.

## 🎯 Funcionalidade
- **Trigger**: Criação de arquivos `.csv.gz` em `s3://[YOUR-BUCKET]/path/`
- **Destino**: ``s3://[YOUR-OTHER-BUCKET]/path/``
- **Estrutura**: Organiza arquivos em pastas baseadas no nome do arquivo

### Exemplo de transformação:
```
Origem:  s3://[YOUR-BUCKET]/path/relatorio_vendas.csv.gz
Destino: s3://[YOUR-OTHER-BUCKET]/path/relatorio_vendas.csv.gz
```

## ⚙️ Configuração

### Variáveis de Ambiente
```bash
EMAIL_SOURCE=no-reply@domain.com.br      # Email remetente para notificações
EMAIL_DESTINATION=admin@domain.com.br     # Email destinatário para alertas
```

### Permissões IAM Necessárias
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:HeadObject"
            ],
            "Resource": [
                "arn:aws:s3:::[YOUR-OTHER-BUCKET]/*",
                "arn:aws:s3:::[YOUR-BUCKET]/path/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "ses:SendEmail",
                "ses:SendRawEmail"
            ],
            "Resource": "*"
        }
    ]
}
```

### Configuração do S3 Trigger
- **Bucket**: `[YOUR-BUCKET]`
- **Prefix**: `path/`
- **Suffix**: `.csv.gz`
- **Event Types**: `s3:ObjectCreated:*`

## 📧 Notificações de Email
A Lambda envia emails automáticos em caso de erro:
- Estrutura de path inválida
- Arquivo de origem não encontrado
- Falha na operação de cópia
- Erros gerais da função

### Configuração do SES
1. Verificar endereços de email no AWS SES
2. Se estiver no sandbox: verificar ambos os emails (origem e destino)
3. Para produção: configurar domínio verificado

## 🔍 Monitoramento
- **Logs**: CloudWatch Logs (`/aws/lambda/[nome-da-funcao]`)
- **Métricas**: CloudWatch Metrics para duração, erros e invocações
- **Emails**: Notificações automáticas em caso de falha

## 🚀 Deployment
1. Fazer upload do código Python
2. Configurar variáveis de ambiente
3. Aplicar permissões IAM
4. Configurar trigger S3
5. Verificar configuração SES
6. Testar com arquivo de exemplo

## ⚠️ Troubleshooting

### Problemas Comuns
- **Email não enviado**: Verificar configuração SES e permissões
- **Arquivo não copiado**: Verificar permissões S3 e estrutura de paths
- **Lambda não executada**: Verificar configuração do trigger S3

### Logs Importantes
```bash
# Verificar logs da Lambda
aws logs filter-log-events --log-group-name /aws/lambda/[nome-da-funcao]

# Verificar métricas
aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Errors
```

---
**Última atualização**: Junho 2025  
**Versão**: 1.0
