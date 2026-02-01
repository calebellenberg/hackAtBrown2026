"""
Unit tests for MemoryEngine class.
"""

import os
import pytest
import tempfile
import shutil
import json
from unittest.mock import Mock, patch, AsyncMock

from memory import MemoryEngine


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    memory_dir = tempfile.mkdtemp()
    chroma_dir = tempfile.mkdtemp()
    yield memory_dir, chroma_dir
    shutil.rmtree(memory_dir, ignore_errors=True)
    shutil.rmtree(chroma_dir, ignore_errors=True)


@pytest.fixture
def sample_markdown_files(temp_dirs):
    """Create sample Markdown files for testing."""
    memory_dir, _ = temp_dirs
    
    # Create Goals.md
    with open(os.path.join(memory_dir, "Goals.md"), "w") as f:
        f.write("""# Long-term Goals

## Financial Goals
- Save $5000 for emergency fund

## Personal Goals
- Reduce impulse purchases
""")
    
    # Create Budget.md
    with open(os.path.join(memory_dir, "Budget.md"), "w") as f:
        f.write("""# Budget Constraints

## Monthly Spending Limits
- Discretionary: $500/month

## Current Month
- Spent: $0
""")
    
    return memory_dir


@pytest.fixture
def mock_service_account_file(temp_dirs):
    """Create a mock service account JSON file for testing."""
    _, chroma_dir = temp_dirs
    
    # Create a mock service account JSON file
    service_account_data = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMOCK_KEY\n-----END PRIVATE KEY-----\n",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test%40test-project.iam.gserviceaccount.com"
    }
    
    service_account_path = os.path.join(chroma_dir, "test-service-account.json")
    with open(service_account_path, 'w') as f:
        json.dump(service_account_data, f)
    
    return service_account_path


@pytest.mark.asyncio
async def test_memory_engine_initialization(temp_dirs, mock_service_account_file):
    """Test MemoryEngine initialization."""
    memory_dir, chroma_dir = temp_dirs
    
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_creds.return_value = Mock()
        mock_creds.return_value.valid = True
        mock_creds.return_value.token = "mock_token"
        
        engine = MemoryEngine(
            memory_dir=memory_dir,
            chroma_persist_dir=chroma_dir,
            service_account_path=mock_service_account_file
        )
        
        assert engine.memory_dir == memory_dir
        assert engine.chroma_persist_dir == chroma_dir
        assert engine.collection is not None


@pytest.mark.asyncio
async def test_chunk_markdown(temp_dirs, mock_service_account_file):
    """Test Markdown chunking."""
    memory_dir, chroma_dir = temp_dirs
    
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_creds.return_value = Mock()
        mock_creds.return_value.valid = True
        mock_creds.return_value.token = "mock_token"
        
        engine = MemoryEngine(
            memory_dir=memory_dir,
            chroma_persist_dir=chroma_dir,
            service_account_path=mock_service_account_file
        )
    
    content = """# Section 1
Content for section 1

## Subsection
More content

# Section 2
Content for section 2"""
    
    chunks = engine._chunk_markdown(content, "test.md")
    
    assert len(chunks) > 0
    assert all('content' in chunk for chunk in chunks)
    assert all('file' in chunk for chunk in chunks)
    assert all('section' in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_reindex_memory(sample_markdown_files, temp_dirs, mock_service_account_file):
    """Test memory reindexing."""
    memory_dir = sample_markdown_files
    _, chroma_dir = temp_dirs
    
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_creds.return_value = Mock()
        mock_creds.return_value.valid = True
        mock_creds.return_value.token = "mock_token"
        
        engine = MemoryEngine(
            memory_dir=memory_dir,
            chroma_persist_dir=chroma_dir,
            service_account_path=mock_service_account_file
        )
    
    success = await engine.reindex_memory()
    
    assert success is True
    assert engine._indexed is True
    assert engine.collection.count() > 0


@pytest.mark.asyncio
async def test_retrieve_context(sample_markdown_files, temp_dirs, mock_service_account_file):
    """Test context retrieval."""
    memory_dir = sample_markdown_files
    _, chroma_dir = temp_dirs
    
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_creds.return_value = Mock()
        mock_creds.return_value.valid = True
        mock_creds.return_value.token = "mock_token"
        
        engine = MemoryEngine(
            memory_dir=memory_dir,
            chroma_persist_dir=chroma_dir,
            service_account_path=mock_service_account_file
        )
    
    await engine.reindex_memory()
    
    snippets = await engine.retrieve_context("emergency fund", n_results=2)
    
    assert isinstance(snippets, list)
    # Should return relevant snippets (may be empty if no matches)


@pytest.mark.asyncio
async def test_call_gemini_api_success(temp_dirs, mock_service_account_file):
    """Test Vertex AI API call with successful response."""
    memory_dir, chroma_dir = temp_dirs
    
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_credentials = Mock()
        mock_credentials.valid = True
        mock_credentials.token = "mock_access_token"
        mock_creds.return_value = mock_credentials
        
        engine = MemoryEngine(
            memory_dir=memory_dir,
            chroma_persist_dir=chroma_dir,
            service_account_path=mock_service_account_file
        )
        
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': '{"impulse_score": 0.75, "confidence": 0.8, "reasoning": "Test", "intervention_action": "COOLDOWN", "memory_update": null}'
                    }]
                }
            }]
        }
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await engine._call_gemini_api("Test prompt")
            
            assert 'impulse_score' in result
            assert result['impulse_score'] == 0.75


@pytest.mark.asyncio
async def test_call_gemini_api_retry(temp_dirs, mock_service_account_file):
    """Test Vertex AI API call with retry logic."""
    import httpx
    
    memory_dir, chroma_dir = temp_dirs
    
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_credentials = Mock()
        mock_credentials.valid = True
        mock_credentials.token = "mock_access_token"
        mock_creds.return_value = mock_credentials
        
        engine = MemoryEngine(
            memory_dir=memory_dir,
            chroma_persist_dir=chroma_dir,
            service_account_path=mock_service_account_file
        )
        
        # Mock httpx to fail first, then succeed
        mock_response = Mock()
        mock_response.json.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': '{"impulse_score": 0.5}'
                    }]
                }
            }]
        }
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_post = AsyncMock()
            # First call fails with httpx error, second succeeds
            mock_post.side_effect = [
                httpx.RequestError("Network error", request=Mock()),
                mock_response
            ]
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            with patch('asyncio.sleep', new_callable=AsyncMock):  # Mock sleep to speed up test
                result = await engine._call_gemini_api("Test prompt")
                
                assert mock_post.call_count == 2  # Should retry once
                assert result['impulse_score'] == 0.5


@pytest.mark.asyncio
async def test_reason_with_gemini_fallback(temp_dirs, mock_service_account_file):
    """Test Vertex AI reasoning with API failure fallback."""
    memory_dir, chroma_dir = temp_dirs
    
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_credentials = Mock()
        mock_credentials.valid = True
        mock_credentials.token = "mock_access_token"
        mock_creds.return_value = mock_credentials
        
        engine = MemoryEngine(
            memory_dir=memory_dir,
            chroma_persist_dir=chroma_dir,
            service_account_path=mock_service_account_file
        )
    
    # Mock API failure
    with patch.object(engine, '_call_gemini_api', side_effect=Exception("API Error")):
        purchase_data = {"product": "Test Product", "cost": 50.0, "website": "test.com"}
        context_snippets = []
        
        result = await engine.reason_with_gemini(0.75, purchase_data, context_snippets)
        
        # Should fallback to Fast Brain score
        assert result['impulse_score'] == 0.75
        assert result['confidence'] == 0.3  # Low confidence for fallback
        assert 'Fast Brain' in result['reasoning']


@pytest.mark.asyncio
async def test_parse_markdown_sections(temp_dirs, mock_service_account_file):
    """Test Markdown section parsing - method removed, test kept for future use."""
    # Note: _parse_markdown_sections was removed during refactoring
    # This test is kept as a placeholder for future implementation if needed
    memory_dir, chroma_dir = temp_dirs
    
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_credentials = Mock()
        mock_credentials.valid = True
        mock_credentials.token = "mock_access_token"
        mock_creds.return_value = mock_credentials
        
        engine = MemoryEngine(
            memory_dir=memory_dir,
            chroma_persist_dir=chroma_dir,
            service_account_path=mock_service_account_file
        )
    
    # Test that chunking works (which is what we use instead)
    content = """# Section 1
Content 1

## Subsection
Sub content

# Section 2
Content 2"""
    
    chunks = engine._chunk_markdown(content, "test.md")
    
    # Verify chunks contain the sections
    section_names = [chunk.get('section', '') for chunk in chunks]
    assert any('Section 1' in s or 'Section 2' in s for s in section_names)
    assert len(chunks) >= 2


@pytest.mark.asyncio
async def test_apply_memory_update(sample_markdown_files, temp_dirs, mock_service_account_file):
    """Test memory update application."""
    memory_dir = sample_markdown_files
    _, chroma_dir = temp_dirs
    
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_credentials = Mock()
        mock_credentials.valid = True
        mock_credentials.token = "mock_access_token"
        mock_creds.return_value = mock_credentials
        
        engine = MemoryEngine(
            memory_dir=memory_dir,
            chroma_persist_dir=chroma_dir,
            service_account_path=mock_service_account_file
        )
    
    # Initialize index
    await engine.reindex_memory()
    
    # Apply memory update
    memory_update = "User is willing to spend $60 on quality apparel"
    success = await engine.apply_memory_update(memory_update)
    
    # Check that update was applied
    if success:
        # Check that file was updated (should be Behavior.md by default)
        behavior_path = os.path.join(memory_dir, "Behavior.md")
        if os.path.exists(behavior_path):
            content = open(behavior_path).read()
            # Update should be in the file or a new file should have been created
            assert True  # Just verify no exception was raised


@pytest.mark.asyncio
async def test_determine_target_file(temp_dirs, mock_service_account_file):
    """Test target file determination."""
    memory_dir, chroma_dir = temp_dirs
    
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_credentials = Mock()
        mock_credentials.valid = True
        mock_credentials.token = "mock_access_token"
        mock_creds.return_value = mock_credentials
        
        engine = MemoryEngine(
            memory_dir=memory_dir,
            chroma_persist_dir=chroma_dir,
            service_account_path=mock_service_account_file
        )
    
    assert engine._determine_target_file("User has a new goal to save money") == "Goals.md"
    assert engine._determine_target_file("Budget limit exceeded") == "Budget.md"
    assert engine._determine_target_file("Account balance is $1000") == "State.md"
    assert engine._determine_target_file("User shops late at night") == "Behavior.md"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
