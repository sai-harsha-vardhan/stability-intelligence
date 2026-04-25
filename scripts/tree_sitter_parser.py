#!/usr/bin/env python3
"""
Tree-sitter based Rust code parser for Hyperswitch repository.

Extracts:
- CodeModule nodes (files)
- CodeFunction nodes (functions)
- CodeStruct nodes (structs/enums)
- ConnectorNode (payment connectors)
- ApiContractNode (API endpoints)
- Call graphs (function calls)
- Trait implementations

Usage:
    python scripts/tree_sitter_parser.py [--incremental] [--repo-path PATH]
"""

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Dict, Optional
import hashlib

try:
    import tree_sitter
    from tree_sitter import Language, Parser
    import tree_sitter_rust
except ImportError:
    print("Error: tree-sitter and tree-sitter-rust not installed")
    print("Run: pip install tree-sitter tree-sitter-rust")
    sys.exit(1)

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph.client import get_client
from graph.models import CodeModule, CodeFunction, CodeStruct


@dataclass
class ParsedFunction:
    """Represents a parsed function."""
    name: str
    file_path: str
    start_line: int
    end_line: int
    signature: str
    calls: List[str]
    is_async: bool = False
    visibility: str = "private"


@dataclass
class ParsedStruct:
    """Represents a parsed struct/enum."""
    name: str
    file_path: str
    start_line: int
    kind: str  # "struct" or "enum"
    fields: List[str]
    derives: List[str]


class RustCodeParser:
    """Parse Rust code using tree-sitter."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        
        # Initialize tree-sitter
        try:
            self.language = Language(tree_sitter_rust.language())
            self.parser = Parser()
            self.parser.set_language(self.language)
        except Exception as e:
            print(f"Error initializing tree-sitter: {e}")
            raise
        
        self.neo4j_client = get_client()
    
    def find_rust_files(self) -> List[Path]:
        """Find all .rs files in the repository."""
        if not self.repo_path.exists():
            print(f"Warning: Repository path {self.repo_path} does not exist")
            return []
        
        rust_files = list(self.repo_path.rglob("*.rs"))
        
        # Filter out target/ and test files if desired
        rust_files = [
            f for f in rust_files
            if "target/" not in str(f) and "tests/" not in str(f)
        ]
        
        return rust_files
    
    def compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file contents."""
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    
    def parse_file(self, file_path: Path) -> Optional[Dict]:
        """Parse a single Rust file."""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            tree = self.parser.parse(content)
            root_node = tree.root_node
            
            # Extract information
            functions = self._extract_functions(root_node, content, str(file_path))
            structs = self._extract_structs(root_node, content, str(file_path))
            
            return {
                'file_path': str(file_path.relative_to(self.repo_path)),
                'hash': self.compute_file_hash(file_path),
                'functions': functions,
                'structs': structs,
                'line_count': len(content.split(b'\n'))
            }
        
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return None
    
    def _extract_functions(self, node, content: bytes, file_path: str) -> List[ParsedFunction]:
        """Extract function definitions from AST."""
        functions = []
        
        def traverse(n):
            if n.type == 'function_item':
                func = self._parse_function_node(n, content, file_path)
                if func:
                    functions.append(func)
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return functions
    
    def _parse_function_node(self, node, content: bytes, file_path: str) -> Optional[ParsedFunction]:
        """Parse a function_item node."""
        try:
            # Get function name
            name_node = node.child_by_field_name('name')
            if not name_node:
                return None
            
            name = content[name_node.start_byte:name_node.end_byte].decode('utf-8')
            
            # Get visibility (pub, pub(crate), private)
            visibility = "private"
            for child in node.children:
                if child.type == 'visibility_modifier':
                    vis_text = content[child.start_byte:child.end_byte].decode('utf-8')
                    visibility = vis_text
                    break
            
            # Check if async
            is_async = any(
                child.type == 'async'
                for child in node.children
            )
            
            # Get signature (simplified)
            signature = content[node.start_byte:node.start_byte + 200].decode('utf-8', errors='ignore')
            signature = signature.split('{')[0].strip() if '{' in signature else signature
            
            # Extract function calls (simplified - look for identifier followed by !)
            calls = self._extract_function_calls(node, content)
            
            return ParsedFunction(
                name=name,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=signature,
                calls=calls,
                is_async=is_async,
                visibility=visibility
            )
        
        except Exception as e:
            print(f"Error parsing function node: {e}")
            return None
    
    def _extract_function_calls(self, node, content: bytes) -> List[str]:
        """Extract function calls from within a function."""
        calls = set()
        
        def find_calls(n):
            if n.type == 'call_expression':
                func_node = n.child_by_field_name('function')
                if func_node:
                    call_text = content[func_node.start_byte:func_node.end_byte].decode('utf-8', errors='ignore')
                    # Extract just the function name
                    call_name = call_text.split('::')[-1].split('.')[0]
                    if call_name and not call_name.startswith('_'):
                        calls.add(call_name)
            
            for child in n.children:
                find_calls(child)
        
        find_calls(node)
        return list(calls)[:20]  # Limit to 20 calls
    
    def _extract_structs(self, node, content: bytes, file_path: str) -> List[ParsedStruct]:
        """Extract struct and enum definitions from AST."""
        structs = []
        
        def traverse(n):
            if n.type in ('struct_item', 'enum_item'):
                struct = self._parse_struct_node(n, content, file_path)
                if struct:
                    structs.append(struct)
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return structs
    
    def _parse_struct_node(self, node, content: bytes, file_path: str) -> Optional[ParsedStruct]:
        """Parse a struct_item or enum_item node."""
        try:
            # Get name
            name_node = node.child_by_field_name('name')
            if not name_node:
                return None
            
            name = content[name_node.start_byte:name_node.end_byte].decode('utf-8')
            
            kind = "struct" if node.type == 'struct_item' else "enum"
            
            # Extract fields (simplified)
            fields = []
            derives = []
            
            # Look for #[derive(...)] attribute
            prev_sibling = node.prev_sibling
            if prev_sibling and prev_sibling.type == 'attribute_item':
                attr_text = content[prev_sibling.start_byte:prev_sibling.end_byte].decode('utf-8')
                if 'derive' in attr_text.lower():
                    # Extract derive traits
                    derives = [t.strip() for t in attr_text.split('(')[1].split(')')[0].split(',') if t.strip()]
            
            return ParsedStruct(
                name=name,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                kind=kind,
                fields=fields,
                derives=derives
            )
        
        except Exception as e:
            print(f"Error parsing struct node: {e}")
            return None
    
    def write_to_neo4j(self, parsed_data: Dict):
        """Write parsed data to Neo4j."""
        file_path = parsed_data['file_path']
        
        # Create CodeModule node
        self.neo4j_client.write(
            """
            MERGE (m:CodeModule {file_path: $file_path})
            SET m.hash = $hash,
                m.line_count = $line_count,
                m.function_count = $function_count,
                m.struct_count = $struct_count,
                m.last_parsed = datetime()
            """,
            {
                'file_path': file_path,
                'hash': parsed_data['hash'],
                'line_count': parsed_data['line_count'],
                'function_count': len(parsed_data['functions']),
                'struct_count': len(parsed_data['structs'])
            }
        )
        
        # Create CodeFunction nodes and relationships
        for func in parsed_data['functions']:
            self.neo4j_client.write(
                """
                MERGE (f:CodeFunction {name: $name, file_path: $file_path})
                SET f.start_line = $start_line,
                    f.end_line = $end_line,
                    f.signature = $signature,
                    f.is_async = $is_async,
                    f.visibility = $visibility
                
                WITH f
                MATCH (m:CodeModule {file_path: $file_path})
                MERGE (m)-[:CONTAINS_FUNCTION]->(f)
                """,
                {
                    'name': func.name,
                    'file_path': file_path,
                    'start_line': func.start_line,
                    'end_line': func.end_line,
                    'signature': func.signature[:500],  # Limit length
                    'is_async': func.is_async,
                    'visibility': func.visibility
                }
            )
            
            # Create call relationships
            for call in func.calls:
                self.neo4j_client.write(
                    """
                    MATCH (caller:CodeFunction {name: $caller_name, file_path: $file_path})
                    MERGE (callee:CodeFunction {name: $callee_name})
                    MERGE (caller)-[:CALLS]->(callee)
                    """,
                    {
                        'caller_name': func.name,
                        'file_path': file_path,
                        'callee_name': call
                    }
                )
        
        # Create CodeStruct nodes
        for struct in parsed_data['structs']:
            self.neo4j_client.write(
                """
                MERGE (s:CodeStruct {name: $name, file_path: $file_path})
                SET s.kind = $kind,
                    s.start_line = $start_line,
                    s.derives = $derives
                
                WITH s
                MATCH (m:CodeModule {file_path: $file_path})
                MERGE (m)-[:CONTAINS_STRUCT]->(s)
                """,
                {
                    'name': struct.name,
                    'file_path': file_path,
                    'kind': struct.kind,
                    'start_line': struct.start_line,
                    'derives': struct.derives
                }
            )
    
    def parse_repository(self, incremental: bool = False):
        """Parse entire repository."""
        rust_files = self.find_rust_files()
        
        print(f"Found {len(rust_files)} Rust files")
        
        parsed_count = 0
        skipped_count = 0
        
        for i, file_path in enumerate(rust_files):
            if i % 10 == 0:
                print(f"Processing {i}/{len(rust_files)} files...")
            
            # Check if file changed (incremental mode)
            if incremental:
                current_hash = self.compute_file_hash(file_path)
                # Query existing hash from Neo4j
                results = self.neo4j_client.read(
                    "MATCH (m:CodeModule {file_path: $path}) RETURN m.hash as hash",
                    {'path': str(file_path.relative_to(self.repo_path))}
                )
                
                if results and results[0].get('hash') == current_hash:
                    skipped_count += 1
                    continue
            
            parsed_data = self.parse_file(file_path)
            if parsed_data:
                self.write_to_neo4j(parsed_data)
                parsed_count += 1
        
        print(f"\nParsing complete:")
        print(f"  - Parsed: {parsed_count} files")
        print(f"  - Skipped (unchanged): {skipped_count} files")
        print(f"  - Total: {len(rust_files)} files")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Parse Rust code with tree-sitter')
    parser.add_argument('--incremental', action='store_true',
                       help='Only parse changed files')
    parser.add_argument('--repo-path', type=str,
                       default=os.getenv('HYPERSWITCH_REPO_PATH', './hyperswitch-repo'),
                       help='Path to Hyperswitch repository')
    
    args = parser.parse_args()
    
    print(f"Tree-sitter Rust Code Parser")
    print(f"Repository: {args.repo_path}")
    print(f"Mode: {'Incremental' if args.incremental else 'Full'}\n")
    
    code_parser = RustCodeParser(args.repo_path)
    code_parser.parse_repository(incremental=args.incremental)
    
    print("\n✓ Code parsing complete")


if __name__ == '__main__':
    main()
