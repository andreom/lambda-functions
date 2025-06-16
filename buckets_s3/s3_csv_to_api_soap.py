import base64
import urllib.parse
import urllib.request
import http.client
import boto3
import os
import datetime
import xml.etree.ElementTree as ET
import ssl
import socket
import json
import logging
import re

# Configuração do logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Clientes AWS inicializados fora do handler para reutilização
s3 = boto3.client('s3')
ses = boto3.client('ses')

def send_notification_email(filename, result, is_error=False):
    """
    Envia um email de notificação via AWS SES com o resultado do processamento.
    
    Args:
        filename (str): Nome do arquivo processado
        result (dict): Resultado do processamento contendo detalhes
        is_error (bool): Flag para indicar se é uma notificação de erro ou sucesso
    """
    try:
        # Configurações do email obtidas de variáveis de ambiente
        sender = os.environ.get('EMAIL_SENDER', 'no-reply@empresa.com.br')                                    # Email remetente (verificado no SES)
        recipients = os.environ.get('EMAIL_RECIPIENTS', 'admin@empresa.com.br,equipe@empresa.com.br)          # Emails destinatários
        cc = os.environ.get('EMAIL_RECIPIENTS','supervisor@empresa.com.br)                                    # Emails em cópia (opcional)

        
        # Definir tipo de notificação e estilo conforme status
        if is_error:
            notification_type = "ERRO"
            status_style = "error"
            status_bg_color = "#FFBABA"
            status_color = "#D8000C"
        else:
            notification_type = "SUCESSO"
            status_style = "success"
            status_bg_color = "#DFF2BF"
            status_color = "#4F8A10"
        
        # Cria o assunto do email
        subject = f"{notification_type} no processamento do arquivo {filename.split('/')[-1]} - Protocolo: {result['protocolo']}"
        
        # Cria o corpo do email em formato HTML
        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .{status_style} {{ color: {status_color}; background-color: {status_bg_color}; padding: 10px; border-radius: 5px; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h2>Notificação de {notification_type} - Envio de Arquivo para SAUDI/VOXIS</h2>
            
            <div class="{status_style}">
                <p><strong>Mensagem:</strong> {result['mensagem']}</p>
            </div>
            
            <h3>Detalhes do Processamento:</h3>
            <table>
                <tr>
                    <th>Item</th>
                    <th>Valor</th>
                </tr>
                <tr>
                    <td>Nome do arquivo</td>
                    <td>{filename.split('/')[-1]}</td>
                </tr>
                <tr>
                    <td>Protocolo</td>
                    <td>{result['protocolo']}</td>
                </tr>
                <tr>
                    <td>Total de Registros</td>
                    <td>{result.get('total_registros', 'N/A')}</td>
                </tr>
                <tr>
                    <td>Linhas Aceitas</td>
                    <td>{result.get('linhas_aceitas', 'N/A')}</td>
                </tr>
                <tr>
                    <td>Linhas Rejeitadas</td>
                    <td>{result.get('linhas_rejeitadas', 'N/A')}</td>
                </tr>
                <tr>
                    <td>Data e Hora</td>
                    <td>{datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</td>
                </tr>
            </table>
            
            <h3>Resposta Completa:</h3>
            <pre>{result.get('resposta_completa', 'N/A')}</pre>
            
            <p>Este é um email automático. Por favor, não responda.</p>
        </body>
        </html>
        """
        
        # Cria o corpo de texto simples do email (para clientes sem suporte a HTML)
        body_text = f"""
        Notificação de {notification_type} - Envio de Arquivo para SAUDI/VOXIS
        
        Mensagem: {result['mensagem']}
        
        Detalhes do Processamento:
        - Nome do arquivo: {filename.split('/')[-1]}
        - Protocolo: {result['protocolo']}
        - Total de Registros: {result.get('total_registros', 'N/A')}
        - Linhas Aceitas: {result.get('linhas_aceitas', 'N/A')}
        - Linhas Rejeitadas: {result.get('linhas_rejeitadas', 'N/A')}
        - Data e Hora: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
        
        Resposta Completa: 
        {result.get('resposta_completa', 'N/A')}
        
        Este é um email automático. Por favor, não responda.
        """
        
        # Envia o email usando o AWS SES
        response = ses.send_email(
            Source=sender,
            Destination={
                'ToAddresses': recipients,
                'CcAddresses': cc
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': body_text,
                        'Charset': 'UTF-8'
                    },
                    'Html': {
                        'Data': body_html,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        
        logger.info(f"Email de notificação de {notification_type} enviado com sucesso. MessageId: {response['MessageId']}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar email de notificação: {str(e)}")
        return False


# Função antiga mantida para compatibilidade com código existente
def send_error_notification_email(filename, result):
    """
    Função legada para manter compatibilidade. Agora chama a função genérica.
    """
    return send_notification_email(filename, result, is_error=True)


def lambda_handler(event, context):
    """
    Função Lambda otimizada para enviar arquivos CSV do S3 para o webservice SAUDI/VOXIS.
    Usa formato SOAP específico com senha em base64 conforme exemplo.
    Implementado apenas com bibliotecas padrão do Python.
    """
    try:
        # Extrair informações do evento
        record = event['Records'][0]
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])

        logger.info(f"Iniciando processamento do arquivo: {key} do bucket: {bucket}")
        
        # Verificação rápida se é um arquivo CSV
        if not key.lower().endswith('.csv'):
            return {'statusCode': 200, 'body': 'Arquivo ignorado: não é CSV'}
        
        # Obter o arquivo do S3
        response = s3.get_object(Bucket=bucket, Key=key)
        file_content = response['Body'].read()
        
        # Configurações do webservice (valores reais armazenados em variáveis de ambiente)
        ws_url=https://exemplo.donain.com.br/webservice/transmiteArquivoService   # URL do webservice SOAP
        ws_login=usuario_webservice                                               # Login para autenticação
        ws_password=senha_webservice                                              # Senha para autenticação
        client_code=codigo_cliente                                                # Código do cliente no sistema
        service_id=BNFC                                                           # ID do serviço (ex: BNFC)
        file_type = os.environ.get('FILE_TYPE', 'CSV')
        
        # Usar o nome original do arquivo (extrair somente o nome do arquivo sem o caminho)
        filename = key.split('/')[-1]
        
        # Codificar senha em base64
        password_base64 = base64.b64encode(ws_password.encode()).decode()
        
        # Codificar conteúdo do arquivo em base64
        file_content_base64 = base64.b64encode(file_content).decode()
        
        # Construir envelope SOAP conforme exemplo fornecido
        soap_envelope = f"""
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:end="http://endpoints.webservice.integration.saudi.acol.com/">
            <soapenv:Header/>
            <soapenv:Body>
                <end:transmitirArquivoOperadora>
                    <login>{ws_login}</login>
                    <senha>{password_base64}</senha>
                    <codCliente>{client_code}</codCliente>
                    <idtServico>{service_id}</idtServico>
                    <tipArquivo>{file_type}</tipArquivo>
                    <nomArquivo>{filename}</nomArquivo>
                    <arquivo>{file_content_base64}</arquivo>
                </end:transmitirArquivoOperadora>
            </soapenv:Body>
        </soapenv:Envelope>
        """.encode('utf-8')
        
        # Extrair o hostname e caminho da URL
        url_parts = urllib.parse.urlparse(ws_url)
        hostname = url_parts.netloc
        path = url_parts.path
        
        # Definir contexto SSL
        ssl_context = ssl.create_default_context()
        if os.environ.get('VERIFY_SSL', '1') == '0':
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        # Configurar timeout - Aumentado para 10 minutos (600 segundos)
        timeout = int(os.environ.get('WS_TIMEOUT', '550'))
        
        # Criar conexão HTTP/HTTPS
        if url_parts.scheme == 'https':
            conn = http.client.HTTPSConnection(hostname, context=ssl_context, timeout=timeout)
        else:
            conn = http.client.HTTPConnection(hostname, timeout=timeout)
        
        # Configurar cabeçalhos
        headers = {
            'Content-Type': 'text/xml;charset=UTF-8',
            'SOAPAction': '',
            'Connection': 'Keep-Alive',
            'Content-Length': str(len(soap_envelope))
        }
        
        # Enviar requisição SOAP
        conn.request('POST', path, body=soap_envelope, headers=headers)
        
        # Obter resposta
        response = conn.getresponse()
        response_data = response.read().decode('utf-8')
        status_code = response.status
        
        # Processar a resposta
        if status_code in (200, 202):
            # Extrair informações detalhadas da resposta SOAP
            try:
                # Registrar resposta completa para debug
                logger.info(f"Resposta completa: {response_data}")
                
                # Método 1: Usando XML ElementTree
                root = ET.fromstring(response_data)
                # Definir namespaces conforme resposta da imagem
                namespaces = {
                    'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
                    'ns2': 'http://endpoints.webservice.integration.saudi.acol.com/'
                }
                
                # Localizar o elemento de retorno
                return_element = root.find('.//ns2:transmitirArquivoOperadoraResponse/return', namespaces)
                
                if return_element is not None and return_element.text:
                    # Extrai as informações específicas da resposta
                    response_text = return_element.text
                    
                    # Extrair informações usando regex para maior robustez
                    success_match = re.search(r'Arquivo inserido com sucesso!', response_text)
                    error_match = re.search(r'Arquivo inserido, mas com erros', response_text)
                    protocolo_match = re.search(r'Número do protocolo\s*:\s*(\d+)', response_text)
                    total_registros_match = re.search(r'Qtd\. Total de Registros\s*:\s*(\d+)', response_text)
                    linhas_aceitas_match = re.search(r'Qtd\. Linhas Aceitas\s*:\s*(\d+)', response_text)
                    linhas_rejeitadas_match = re.search(r'Qtd\. Linhas Rejeitadas\s*:\s*(\d+)', response_text)
                    
                    # Verificar se a resposta indica erro
                    has_error = error_match is not None
                    status_message = error_match.group(0) if error_match else (success_match.group(0) if success_match else 'Arquivo processado')
                    
                    # Construir objeto de resposta estruturado
                    result = {
                        'status': 'Erro' if has_error else 'Sucesso',
                        'mensagem': status_message,
                        'protocolo': protocolo_match.group(1) if protocolo_match else 'N/A',
                        'total_registros': total_registros_match.group(1) if total_registros_match else '0',
                        'linhas_aceitas': linhas_aceitas_match.group(1) if linhas_aceitas_match else '0',
                        'linhas_rejeitadas': linhas_rejeitadas_match.group(1) if linhas_rejeitadas_match else '0',
                        'resposta_completa': response_text
                    }
                    
                    # Enviar email conforme o resultado (erro ou sucesso)
                    if has_error:
                        send_notification_email(key, result, is_error=True)
                    else:
                        send_notification_email(key, result, is_error=False)
                else:
                    # Método 2: Extração direta por regex se ElementTree falhar
                    success_match = re.search(r'Arquivo inserido com sucesso!', response_data)
                    error_match = re.search(r'Arquivo inserido, mas com erros', response_data)
                    protocolo_match = re.search(r'Número do protocolo\s*:\s*(\d+)', response_data)
                    total_registros_match = re.search(r'Qtd\. Total de Registros\s*:\s*(\d+)', response_data)
                    linhas_aceitas_match = re.search(r'Qtd\. Linhas Aceitas\s*:\s*(\d+)', response_data)
                    linhas_rejeitadas_match = re.search(r'Qtd\. Linhas Rejeitadas\s*:\s*(\d+)', response_data)
                    
                    # Verificar se a resposta indica erro
                    has_error = error_match is not None
                    status_message = error_match.group(0) if error_match else (success_match.group(0) if success_match else 'Arquivo processado')
                    
                    result = {
                        'status': 'Erro' if has_error else 'Sucesso',
                        'mensagem': status_message,
                        'protocolo': protocolo_match.group(1) if protocolo_match else 'N/A',
                        'total_registros': total_registros_match.group(1) if total_registros_match else '0',
                        'linhas_aceitas': linhas_aceitas_match.group(1) if linhas_aceitas_match else '0',
                        'linhas_rejeitadas': linhas_rejeitadas_match.group(1) if linhas_rejeitadas_match else '0',
                        'resposta_completa': response_data[:500]  # Limita o tamanho para não sobrecarregar logs
                    }
                    
                    # Enviar email conforme o resultado (erro ou sucesso)
                    if has_error:
                        send_notification_email(key, result, is_error=True)
                    else:
                        send_notification_email(key, result, is_error=False)
            except Exception as xml_error:
                logger.error(f"Erro ao processar XML: {str(xml_error)}")
                result = {
                    'status': 'Erro de processamento',
                    'mensagem': f"Erro ao processar resposta XML: {str(xml_error)}",
                    'resposta_completa': response_data[:500]
                }
                # Enviar email de erro para problemas no processamento do XML
                send_notification_email(key, result, is_error=True)
            
            # Em caso de sucesso, opcionalmente move o arquivo para pasta de processados
            if os.environ.get('MOVE_PROCESSED') == 'true':
                processed_path = os.environ.get('PROCESSED_PATH', 'processados/')
                processed_key = processed_path + key.split('/')[-1]
                
                s3.copy_object(
                    Bucket=bucket,
                    CopySource={'Bucket': bucket, 'Key': key},
                    Key=processed_key
                )
                
                if os.environ.get('DELETE_ORIGINAL') == 'true':
                    s3.delete_object(Bucket=bucket, Key=key)
            
            return {
                'statusCode': 200,
                'body': json.dumps(result)
            }
        else:
            # Em caso de erro, tenta extrair mensagem de erro da resposta
            try:
                root = ET.fromstring(response_data)
                namespaces = {
                    'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
                    'ns2': 'http://endpoints.webservice.integration.saudi.acol.com/'
                }
                fault = root.find('.//soap:Fault', namespaces)
                if fault is not None:
                    fault_string = fault.find('faultstring')
                    error_msg = fault_string.text if fault_string is not None else response_data[:200]
                else:
                    error_msg = f"Erro de comunicação. Status: {status_code}. Resposta: {response_data[:200]}"
            except Exception as e:
                error_msg = f"Erro de comunicação. Status: {status_code}. Resposta: {response_data[:200]}"
            
            # Criar objeto de resultado para erro de comunicação
            error_result = {
                'status': 'Erro',
                'mensagem': error_msg,
                'protocolo': 'N/A',
                'resposta_completa': response_data[:500]
            }
            
            # Enviar email de notificação para erro de comunicação
            send_notification_email(key, error_result, is_error=True)
            
            # Em caso de erro, opcionalmente move o arquivo para pasta de erros
            if os.environ.get('MOVE_FAILED') == 'true':
                error_path = os.environ.get('ERROR_PATH', 'erros/')
                error_key = error_path + key.split('/')[-1]
                
                s3.copy_object(
                    Bucket=bucket,
                    CopySource={'Bucket': bucket, 'Key': key},
                    Key=error_key
                )
            
            return {
                'statusCode': 500,
                'body': json.dumps(error_result)
            }
    
    except Exception as e:
        logger.error(f"Erro geral: {str(e)}")
        error_result = {
            'status': 'Erro',
            'mensagem': str(e),
            'protocolo': 'N/A',
            'resposta_completa': 'Exceção não tratada'
        }
        
        # Tentar enviar email mesmo em caso de erro geral
        try:
            # Usa o nome do arquivo do evento, se disponível
            filename = event['Records'][0]['s3']['object']['key'] if 'Records' in event and len(event['Records']) > 0 else 'unknown_file'
            send_notification_email(filename, error_result, is_error=True)
        except:
            logger.error("Não foi possível enviar email de notificação para o erro geral")
        
        return {
            'statusCode': 500, 
            'body': json.dumps({
                'status': 'Erro',
                'mensagem': str(e)
            })
        }
