"""
Testes unitários para s3_copy_fail_email.py

Para executar os testes:
    pytest tests/test_s3_copy_fail_email.py -v
"""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Importar o módulo a ser testado
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'buckets_s3'))
import s3_copy_fail_email


class TestValidateEnvironmentVariables:
    """Testes para a função validate_environment_variables"""

    def test_all_variables_present(self):
        """Teste quando todas as variáveis estão presentes"""
        with patch.dict(os.environ, {'VAR1': 'value1', 'VAR2': 'value2'}):
            # Não deve lançar exceção
            s3_copy_fail_email.validate_environment_variables(['VAR1', 'VAR2'])

    def test_missing_variables(self):
        """Teste quando variáveis estão ausentes"""
        with patch.dict(os.environ, {'VAR1': 'value1'}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                s3_copy_fail_email.validate_environment_variables(['VAR1', 'VAR2', 'VAR3'])

            assert 'VAR2' in str(exc_info.value)
            assert 'VAR3' in str(exc_info.value)


class TestSendErrorEmail:
    """Testes para a função send_error_email"""

    @patch('s3_copy_fail_email.ses_client')
    def test_send_email_success(self, mock_ses):
        """Teste envio de email com sucesso"""
        mock_ses.send_email.return_value = {'MessageId': 'test-message-id'}

        result = s3_copy_fail_email.send_error_email(
            "Test error message",
            {'function_name': 'test-function'}
        )

        assert result is True
        mock_ses.send_email.assert_called_once()

    @patch('s3_copy_fail_email.ses_client')
    def test_send_email_failure(self, mock_ses):
        """Teste falha no envio de email"""
        mock_ses.send_email.side_effect = Exception("SES Error")

        result = s3_copy_fail_email.send_error_email("Test error", {})

        assert result is False


class TestRetryDecorator:
    """Testes para o decorador retry_on_failure"""

    def test_success_on_first_attempt(self):
        """Teste função que tem sucesso na primeira tentativa"""
        mock_func = Mock(return_value="success")
        decorated_func = s3_copy_fail_email.retry_on_failure(max_retries=3)(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 1

    def test_success_after_retries(self):
        """Teste função que tem sucesso após algumas tentativas"""
        mock_func = Mock(side_effect=[Exception("Error 1"), Exception("Error 2"), "success"])
        decorated_func = s3_copy_fail_email.retry_on_failure(max_retries=3, initial_delay=0.1)(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 3

    def test_failure_after_all_retries(self):
        """Teste função que falha após todas as tentativas"""
        mock_func = Mock(side_effect=Exception("Persistent Error"))
        decorated_func = s3_copy_fail_email.retry_on_failure(max_retries=3, initial_delay=0.1)(mock_func)

        with pytest.raises(Exception) as exc_info:
            decorated_func()

        assert "Persistent Error" in str(exc_info.value)
        assert mock_func.call_count == 3


class TestLambdaHandler:
    """Testes para a função lambda_handler"""

    @pytest.fixture
    def mock_context(self):
        """Fixture para criar contexto mock"""
        context = Mock()
        context.function_name = "test-function"
        context.function_version = "$LATEST"
        context.aws_request_id = "test-request-id"
        return context

    @pytest.fixture
    def s3_event(self):
        """Fixture para criar evento S3 mock"""
        return {
            'Records': [
                {
                    's3': {
                        'bucket': {'name': 'test-source-bucket'},
                        'object': {'key': 'voxis/test-file.csv.gz'}
                    },
                    'eventName': 'ObjectCreated:Put'
                }
            ]
        }

    @patch.dict(os.environ, {
        'EMAIL_SOURCE': 'test@example.com',
        'EMAIL_DESTINATION': 'admin@example.com',
        'SOURCE_BUCKET': 'test-source-bucket',
        'DESTINATION_BUCKET': 'test-dest-bucket',
        'DESTINATION_PREFIX': 'voxis/processed'
    })
    @patch('s3_copy_fail_email.s3_client')
    def test_successful_copy(self, mock_s3, s3_event, mock_context):
        """Teste cópia bem-sucedida de arquivo"""
        # Simular que o arquivo existe
        mock_s3.head_object.return_value = {}
        mock_s3.copy_object.return_value = {}

        result = s3_copy_fail_email.lambda_handler(s3_event, mock_context)

        assert result['statusCode'] == 200
        assert mock_s3.copy_object.called

    @patch.dict(os.environ, {
        'EMAIL_SOURCE': 'test@example.com',
        'EMAIL_DESTINATION': 'admin@example.com'
    })
    def test_missing_environment_variables(self, s3_event, mock_context):
        """Teste quando variáveis de ambiente obrigatórias estão ausentes"""
        # Remover variáveis obrigatórias
        with patch.dict(os.environ, {}, clear=True):
            result = s3_copy_fail_email.lambda_handler(s3_event, mock_context)

            assert result['statusCode'] == 500
            assert 'error' in json.loads(result['body'])

    @patch.dict(os.environ, {
        'EMAIL_SOURCE': 'test@example.com',
        'EMAIL_DESTINATION': 'admin@example.com',
        'SOURCE_BUCKET': 'test-source-bucket'
    })
    def test_wrong_bucket(self, mock_context):
        """Teste quando o arquivo vem de um bucket diferente"""
        event = {
            'Records': [
                {
                    's3': {
                        'bucket': {'name': 'wrong-bucket'},
                        'object': {'key': 'voxis/test.csv.gz'}
                    },
                    'eventName': 'ObjectCreated:Put'
                }
            ]
        }

        result = s3_copy_fail_email.lambda_handler(event, mock_context)

        # Deve ignorar o arquivo e retornar sucesso
        assert result['statusCode'] == 200

    @patch.dict(os.environ, {
        'EMAIL_SOURCE': 'test@example.com',
        'EMAIL_DESTINATION': 'admin@example.com',
        'SOURCE_BUCKET': 'test-source-bucket'
    })
    def test_non_csv_file(self, mock_context):
        """Teste quando o arquivo não é CSV.GZ"""
        event = {
            'Records': [
                {
                    's3': {
                        'bucket': {'name': 'test-source-bucket'},
                        'object': {'key': 'voxis/test.txt'}
                    },
                    'eventName': 'ObjectCreated:Put'
                }
            ]
        }

        result = s3_copy_fail_email.lambda_handler(event, mock_context)

        # Deve ignorar o arquivo e retornar sucesso
        assert result['statusCode'] == 200


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
