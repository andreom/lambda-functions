import boto3
import logging
import json
import os
import time
from urllib.parse import unquote_plus
from datetime import datetime
from functools import wraps

# Configurar logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Inicializar clientes AWS
s3_client = boto3.client('s3')
ses_client = boto3.client('ses')

# Configurações de email
EMAIL_SOURCE = os.environ.get('EMAIL_SOURCE', 'no-reply@domain.com.br')
EMAIL_DESTINATION = os.environ.get('EMAIL_DESTINATION', 'admin@domain.com.br')
EMAIL_SUBJECT_PREFIX = '[LAMBDA ERROR] Falha na cópia de arquivos S3'

def validate_environment_variables(required_vars):
    """
    Valida se todas as variáveis de ambiente obrigatórias estão configuradas.

    Args:
        required_vars (list): Lista de nomes de variáveis obrigatórias

    Raises:
        ValueError: Se alguma variável obrigatória estiver ausente
    """
    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)

    if missing_vars:
        error_msg = f"Variáveis de ambiente obrigatórias ausentes: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"[SUCCESS] All required environment variables are configured: {', '.join(required_vars)}")

def validate_email_format(email):
    """
    Valida formato de endereço de email.

    Args:
        email (str): Endereço de email para validar

    Returns:
        bool: True se o email é válido, False caso contrário
    """
    import re
    EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    if not email or not EMAIL_REGEX.match(email):
        logger.error(f"Invalid email format: {email}")
        return False
    return True

def retry_on_failure(max_retries=3, initial_delay=1, backoff_factor=2):
    """
    Decorador para adicionar retry com backoff exponencial.

    Args:
        max_retries (int): Número máximo de tentativas
        initial_delay (int): Delay inicial em segundos
        backoff_factor (int): Fator de multiplicação para cada retry

    Returns:
        Decorator function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Tentativa {attempt + 1}/{max_retries} falhou para {func.__name__}: {str(e)}. "
                            f"Aguardando {delay}s antes de tentar novamente..."
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(f"Todas as {max_retries} tentativas falharam para {func.__name__}")

            raise last_exception
        return wrapper
    return decorator

@retry_on_failure(max_retries=3, initial_delay=1, backoff_factor=2)
def send_error_email(error_message, context_info=None):
    """
    Envia email de notificação em caso de erro
    """
    try:
        # Preparar o corpo do email
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        email_body = f"""
        ERRO DETECTADO NA LAMBDA DE CÓPIA S3
        
        Timestamp: {timestamp}
        Lambda Function: {context_info.get('function_name', 'N/A') if context_info else 'N/A'}
        
        DETALHES DO ERRO:
        {error_message}
        
        INFORMAÇÕES ADICIONAIS:
        {json.dumps(context_info, indent=2) if context_info else 'Nenhuma informação adicional disponível'}
        
        Este é um email automático gerado pela função Lambda.
        Por favor, verifique os logs do CloudWatch para mais detalhes.
        """
        
        # Enviar email
        response = ses_client.send_email(
            Source=EMAIL_SOURCE,
            Destination={
                'ToAddresses': [EMAIL_DESTINATION]
            },
            Message={
                'Subject': {
                    'Data': f"{EMAIL_SUBJECT_PREFIX} - {timestamp}",
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': email_body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        
        logger.info(f"[SUCCESS] Email de erro enviado com sucesso. MessageId: {response['MessageId']}")
        return True
        
    except Exception as email_error:
        logger.error(f"[ERROR] Falha ao enviar email de notificação: {str(email_error)}")
        logger.error(f"   Email origem: {EMAIL_SOURCE}")
        logger.error(f"   Email destino: {EMAIL_DESTINATION}")
        return False

def lambda_handler(event, context):
    """
    Função Lambda para copiar arquivos CSV entre buckets
    Trigger: Criação de arquivos .csv em S3
    """

    # Validar variáveis de ambiente obrigatórias
    try:
        validate_environment_variables(['EMAIL_SOURCE', 'EMAIL_DESTINATION'])
    except ValueError as e:
        logger.error(f"Erro de configuração: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

    # Definir buckets a partir de variáveis de ambiente
    SOURCE_BUCKET = os.environ.get('SOURCE_BUCKET', 'ferj-prod-snowflake-relatorio')
    DESTINATION_BUCKET = os.environ.get('DESTINATION_BUCKET', 'ferj-prod-integracao')
    DESTINATION_PREFIX = os.environ.get('DESTINATION_PREFIX', 'voxis/VIEWS_VOXIS_SAUDI_UNIMED_FERJ_SCHEMA')

    # Informações do contexto para email
    context_info = {
        'function_name': context.function_name if context else 'N/A',
        'function_version': context.function_version if context else 'N/A',
        'request_id': context.aws_request_id if context else 'N/A',
        'source_bucket': SOURCE_BUCKET,
        'destination_bucket': DESTINATION_BUCKET
    }
    
    # Validar estrutura do evento
    if 'Records' not in event or not event['Records']:
        logger.warning("No Records found in S3 event")
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'No records to process'})
        }

    logger.info(f"Iniciando execução da Lambda com {len(event['Records'])} record(s)")
    logger.info(f"Bucket origem: {SOURCE_BUCKET}")
    logger.info(f"Bucket destino: {DESTINATION_BUCKET}")
    logger.debug(f"Email configurado - Origem: {EMAIL_SOURCE}, Destino: {EMAIL_DESTINATION}")

    # Tracking de arquivos processados
    processed_count = 0
    skipped_count = 0
    error_count = 0

    try:
        # Processar cada registro do evento S3
        for record in event['Records']:
            
            # Extrair informações do evento
            source_bucket = record['s3']['bucket']['name']
            object_key = unquote_plus(record['s3']['object']['key'])
            event_name = record['eventName']
            
            logger.info(f"Processando arquivo: {object_key} no bucket: {source_bucket}")
            logger.info(f"Tipo de evento: {event_name}")
            
            # Verificar se é o bucket correto
            if source_bucket != SOURCE_BUCKET:
                logger.warning(f"Bucket {source_bucket} não é o esperado ({SOURCE_BUCKET}) - ignorado")
                continue
            
            # Verificar se é um evento de criação/put
            if not event_name.startswith('ObjectCreated'):
                logger.info(f"Evento {event_name} ignorado - não é criação de objeto")
                continue
            
            # Verificar se o arquivo está no caminho correto
            if not object_key.startswith('voxis/'):
                logger.info(f"Arquivo {object_key} não está no path voxis/ - ignorado")
                continue
            
            # Verificar se é um arquivo CSV
            if not object_key.lower().endswith('.csv.gz'):
                logger.info(f"Arquivo {object_key} não é CSV.GZIP - ignorado")
                continue
            
            # Extrair apenas o nome do arquivo (sem extensão)
            file_path_parts = object_key.split('/')
            if len(file_path_parts) < 2:
                error_msg = f"Estrutura de path inválida: {object_key}"
                logger.warning(error_msg)
                
                # Enviar email de notificação
                email_context = context_info.copy()
                email_context['error_type'] = 'PATH_STRUCTURE_ERROR'
                email_context['object_key'] = object_key
                
                email_sent = send_error_email(error_msg, email_context)
                logger.info(f"Status envio email para erro de estrutura: {'Sucesso' if email_sent else 'Falha'}")
                continue
                
            filename_with_ext = file_path_parts[-1]  # último elemento
            filename_without_ext = filename_with_ext.replace('.csv.gz', '').replace('.CSV.GZ', '')
            
            logger.info(f"Nome do arquivo extraído: {filename_without_ext}")

            # Construir o path de destino
            destination_key = f"{DESTINATION_PREFIX}/{filename_without_ext.upper()}/{filename_with_ext}"
            
            logger.info(f"Path de origem: s3://{source_bucket}/{object_key}")
            logger.info(f"Path de destino: s3://{DESTINATION_BUCKET}/{destination_key}")
            
            # Verificar se o arquivo de origem existe
            try:
                s3_client.head_object(Bucket=source_bucket, Key=object_key)
                logger.info(f"Arquivo de origem confirmado: s3://{source_bucket}/{object_key}")
            except Exception as e:
                error_msg = f"Erro ao verificar arquivo de origem: {str(e)}"
                logger.error(error_msg)
                
                # Enviar email de notificação
                email_context = context_info.copy()
                email_context['error_type'] = 'SOURCE_FILE_NOT_FOUND'
                email_context['object_key'] = object_key
                email_context['source_bucket'] = source_bucket
                
                email_sent = send_error_email(error_msg, email_context)
                logger.error(f"Status envio email para erro de verificação: {'Sucesso' if email_sent else 'Falha'}")
                continue
            
            # Realizar a cópia entre buckets
            copy_source = {
                'Bucket': source_bucket,
                'Key': object_key
            }
            
            try:
                s3_client.copy_object(
                    CopySource=copy_source,
                    Bucket=DESTINATION_BUCKET,
                    Key=destination_key
                )
                
                logger.info(f"[SUCCESS] Arquivo copiado com sucesso!")
                logger.info(f"   Origem: s3://{source_bucket}/{object_key}")
                logger.info(f"   Destino: s3://{DESTINATION_BUCKET}/{destination_key}")
                
                # Verificar se a cópia foi bem-sucedida
                s3_client.head_object(Bucket=DESTINATION_BUCKET, Key=destination_key)
                logger.info(f"[SUCCESS] Cópia verificada no destino")
                
            except Exception as e:
                error_msg = f"Erro ao copiar arquivo: {str(e)}"
                logger.error(f"[ERROR] {error_msg}")
                logger.error(f"   Origem: s3://{source_bucket}/{object_key}")
                logger.error(f"   Destino: s3://{DESTINATION_BUCKET}/{destination_key}")
                
                # Enviar email de notificação
                email_context = context_info.copy()
                email_context['error_type'] = 'COPY_OPERATION_ERROR'
                email_context['object_key'] = object_key
                email_context['source_bucket'] = source_bucket
                email_context['destination_bucket'] = DESTINATION_BUCKET
                email_context['destination_key'] = destination_key
                
                email_sent = send_error_email(error_msg, email_context)
                logger.error(f"Status envio email para erro de cópia: {'Sucesso' if email_sent else 'Falha'}")
                continue
    
    except Exception as e:
        error_msg = f"Erro geral na execução da Lambda: {str(e)}"
        logger.error(f"[ERROR] {error_msg}")
        logger.error(f"Event completo: {json.dumps(event)}")
        
        # Enviar email de notificação para erro geral
        email_context = context_info.copy()
        email_context['error_type'] = 'GENERAL_LAMBDA_ERROR'
        email_context['event'] = event
        
        email_sent = send_error_email(error_msg, email_context)
        logger.error(f"Status envio email para erro geral: {'Sucesso' if email_sent else 'Falha'}")
        
        raise
    
    logger.info("[COMPLETED] Execução da Lambda finalizada com sucesso")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Processamento concluído com sucesso',
            'processed_files': len(event['Records'])
        })
    }
