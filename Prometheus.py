# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import time
import json
from datetime import datetime
import subprocess
import sys
import queue
import zipfile
from pathlib import Path
import re
import base64
from PIL import Image, ImageTk, ImageOps

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

class ConversationManager:
    """Gestionnaire robuste des conversations"""
    
    def __init__(self):
        self.conversations_dir = "conversations"
        self.ensure_directory()
    
    def ensure_directory(self):
        """Crée le dossier conversations s'il n'existe pas"""
        if not os.path.exists(self.conversations_dir):
            os.makedirs(self.conversations_dir)
    
    def repair_json_file(self, file_path):
        """Répare un fichier JSON corrompu"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            # Tentative de réparation basique
            if not content:
                return self.create_default_conversation(file_path)
            
            # Essaye de charger le JSON
            try:
                data = json.loads(content)
                return data
            except json.JSONDecodeError as e:
                print(f"Réparation du fichier {file_path}: {e}")
                
                # Si le fichier est gravement corrompu, on le sauvegarde et crée un nouveau
                backup_path = f"{file_path}.backup_{int(time.time())}"
                if os.path.exists(file_path):
                    os.rename(file_path, backup_path)
                return self.create_default_conversation(file_path)
                
        except Exception as e:
            print(f"Erreur lors de la réparation de {file_path}: {e}")
            return self.create_default_conversation(file_path)
    
    def create_default_conversation(self, file_path):
        """Crée une conversation par défaut"""
        conv_id = os.path.splitext(os.path.basename(file_path))[0]
        return {
            "id": conv_id,
            "title": "Conversation réparée",
            "messages": [],
            "timestamp": datetime.now().isoformat()
        }
    
    def load_conversation_file(self, file_path):
        """Charge un fichier de conversation avec réparation automatique"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validation de la structure
            if not isinstance(data, dict):
                return self.repair_json_file(file_path)
            
            required_fields = ['id', 'title', 'messages']
            for field in required_fields:
                if field not in data:
                    default_data = self.create_default_conversation(file_path)
                    data[field] = default_data[field]
            
            # Validation des messages
            if not isinstance(data['messages'], list):
                data['messages'] = []
            else:
                # Nettoyage des messages
                cleaned_messages = []
                for msg in data['messages']:
                    if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
                        if 'timestamp' not in msg or not isinstance(msg['timestamp'], str):
                            msg['timestamp'] = datetime.now().isoformat()
                        cleaned_messages.append(msg)
                data['messages'] = cleaned_messages
            
            return data
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Erreur de chargement {file_path}: {e}")
            return self.repair_json_file(file_path)
    
    def save_conversation(self, conversation):
        """Sauvegarde une conversation de manière sécurisée"""
        try:
            file_path = os.path.join(self.conversations_dir, f"{conversation['id']}.json")
            
            # Sauvegarde temporaire d'abord
            temp_path = f"{file_path}.tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(conversation, f, ensure_ascii=False, indent=2)
            
            # Remplace le fichier original
            if os.path.exists(file_path):
                os.remove(file_path)
            os.rename(temp_path, file_path)
            
            return True
        except Exception as e:
            print(f"Erreur sauvegarde conversation: {e}")
            return False

class CodeTextWidget:
    """Widget pour afficher du code avec coloration syntaxique basique"""
    
    def __init__(self, parent, language="text"):
        self.frame = tk.Frame(parent, bg='#1e1e1e', relief='solid', bd=1)
        self.language = language
        
        # Header avec le nom du langage
        header_frame = tk.Frame(self.frame, bg='#2d2d30', height=25)
        header_frame.pack(fill='x', side='top')
        header_frame.pack_propagate(False)
        
        lang_label = tk.Label(header_frame, text=language.upper(), 
                            bg='#2d2d30', fg='#cccccc', font=('Consolas', 9, 'bold'))
        lang_label.pack(side='left', padx=10)
        
        # Boutons d'action
        button_frame = tk.Frame(header_frame, bg='#2d2d30')
        button_frame.pack(side='right', padx=5)
        
        copy_btn = tk.Button(button_frame, text="📋 Copier", 
                           command=self.copy_code,
                           bg='#2d2d30', fg='#cccccc',
                           font=('Segoe UI', 8),
                           relief='flat', bd=0,
                           cursor='hand2')
        copy_btn.pack(side='left', padx=2)
        
        # Bouton pour agrandir/réduire
        self.expand_btn = tk.Button(button_frame, text="⬇️ Agrandir", 
                                  command=self.toggle_expand,
                                  bg='#2d2d30', fg='#cccccc',
                                  font=('Segoe UI', 8),
                                  relief='flat', bd=0,
                                  cursor='hand2')
        self.expand_btn.pack(side='left', padx=2)
        
        self.is_expanded = False
        
        # Créer un PanedWindow pour permettre le redimensionnement
        self.paned = tk.PanedWindow(self.frame, orient='vertical', 
                                  bg='#1e1e1e', sashwidth=4, sashrelief='raised')
        self.paned.pack(fill='both', expand=True)
        
        # Cadre pour la zone de texte avec scrollbar
        text_frame = tk.Frame(self.paned, bg='#1e1e1e')
        self.paned.add(text_frame)
        
        # Barres de défilement
        v_scrollbar = ttk.Scrollbar(text_frame, orient='vertical')
        h_scrollbar = ttk.Scrollbar(text_frame, orient='horizontal')
        
        # Zone de texte pour le code avec TOUTES les lignes
        self.text_widget = tk.Text(
            text_frame, 
            wrap=tk.NONE,  # Pas de retour à la ligne pour voir tout le code
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='#ffffff',
            selectbackground='#264f78',
            font=('Consolas', 10),
            padx=10,
            pady=10,
            relief='flat',
            bd=0,
            yscrollcommand=v_scrollbar.set,
            xscrollcommand=h_scrollbar.set
        )
        
        # Configurer les scrollbars
        v_scrollbar.config(command=self.text_widget.yview)
        h_scrollbar.config(command=self.text_widget.xview)
        
        # Packer les éléments
        self.text_widget.pack(side='left', fill='both', expand=True)
        v_scrollbar.pack(side='right', fill='y')
        h_scrollbar.pack(side='bottom', fill='x')
        
        self.text_widget.config(state='disabled')
    
    def set_code(self, code):
        """Définit le code à afficher"""
        self.text_widget.config(state='normal')
        self.text_widget.delete('1.0', tk.END)
        self.text_widget.insert('1.0', code)
        
        # Compter le nombre de lignes et ajuster la hauteur
        num_lines = code.count('\n') + 1
        if num_lines > 50:
            # Pour les codes très longs, mettre plus de lignes
            self.text_widget.config(height=min(num_lines, 100))
        else:
            self.text_widget.config(height=num_lines + 2)  # +2 pour la marge
        
        self.apply_basic_syntax_highlighting()
        self.text_widget.config(state='disabled')
    
    def toggle_expand(self):
        """Agrandit ou réduit la fenêtre de code"""
        if not self.is_expanded:
            # Agrandir
            self.frame.winfo_toplevel().geometry("1400x900")
            self.expand_btn.config(text="⬆️ Réduire")
            self.text_widget.config(height=40)  # Hauteur agrandie
        else:
            # Réduire
            self.frame.winfo_toplevel().geometry("1200x700")
            self.expand_btn.config(text="⬇️ Agrandir")
            # Remettre la hauteur par défaut
            code = self.text_widget.get('1.0', tk.END)
            num_lines = code.count('\n') + 1
            self.text_widget.config(height=min(num_lines, 20))
        
        self.is_expanded = not self.is_expanded
    
    def copy_code(self):
        """Copie le code dans le presse-papier"""
        code = self.text_widget.get('1.0', tk.END).strip()
        self.text_widget.master.master.clipboard_clear()
        self.text_widget.master.master.clipboard_append(code)
        # Message flash de confirmation
        self.show_copy_confirmation()
    
    def show_copy_confirmation(self):
        """Affiche une confirmation de copie"""
        confirm = tk.Label(self.frame, text="✓ Copié!", 
                         bg='#4caf50', fg='white', font=('Segoe UI', 8))
        confirm.place(relx=0.85, rely=0.05, anchor='ne')
        self.frame.after(2000, confirm.destroy)
    
    def apply_basic_syntax_highlighting(self):
        """Applique une coloration syntaxique basique"""
        if self.language == "python":
            self.highlight_python()
        elif self.language in ["cpp", "c++", "c"]:
            self.highlight_cpp()
        elif self.language == "javascript":
            self.highlight_javascript()
        elif self.language == "html":
            self.highlight_html()
        elif self.language == "css":
            self.highlight_css()
    
    def highlight_python(self):
        """Coloration syntaxique Python"""
        keywords = ['def', 'class', 'if', 'else', 'elif', 'for', 'while', 'import', 
                   'from', 'as', 'return', 'try', 'except', 'finally', 'with', 'lambda']
        builtins = ['print', 'range', 'len', 'str', 'int', 'float', 'list', 'dict']
        
        self.highlight_pattern(keywords, '#569cd6')  # Bleu pour les keywords
        self.highlight_pattern(builtins, '#4ec9b0')  # Cyan pour les builtins
        self.highlight_pattern(r'#.*$', '#6a9955')   # Vert pour les commentaires
        self.highlight_pattern(r'(".*?")|(\'.*?\')', '#ce9178')  # Orange pour les strings
        self.highlight_pattern(r'\b\d+\b', '#b5cea8')  # Vert clair pour les nombres
    
    def highlight_cpp(self):
        """Coloration syntaxique C++"""
        keywords = ['class', 'struct', 'void', 'int', 'float', 'double', 'bool', 'char',
                   'if', 'else', 'for', 'while', 'return', 'using', 'namespace', 'include']
        
        self.highlight_pattern(keywords, '#569cd6')
        self.highlight_pattern(r'//.*$', '#6a9955')
        self.highlight_pattern(r'(".*?")|(\'.*?\')', '#ce9178')
        self.highlight_pattern(r'\b\d+\b', '#b5cea8')
    
    def highlight_javascript(self):
        """Coloration syntaxique JavaScript"""
        keywords = ['function', 'var', 'let', 'const', 'if', 'else', 'for', 'while', 
                   'return', 'class', 'import', 'export', 'async', 'await']
        
        self.highlight_pattern(keywords, '#569cd6')
        self.highlight_pattern(r'//.*$', '#6a9955')
        self.highlight_pattern(r'(".*?")|(\'.*?\')|(`.*?`)', '#ce9178')
        self.highlight_pattern(r'\b\d+\b', '#b5cea8')
    
    def highlight_html(self):
        """Coloration syntaxique HTML"""
        self.highlight_pattern(r'&lt;/?[^&gt;]+&gt;', '#569cd6')
        self.highlight_pattern(r'&lt;!--.*?--&gt;', '#6a9955')
        self.highlight_pattern(r'(".*?")|(\'[^\']*\')', '#ce9178')
    
    def highlight_css(self):
        """Coloration syntaxique CSS"""
        self.highlight_pattern(r'\.[a-zA-Z][\w-]*', '#d7ba7d')
        self.highlight_pattern(r'#[a-zA-Z][\w-]*', '#d7ba7d')
        self.highlight_pattern(r'//.*$', '#6a9955')
        self.highlight_pattern(r'("[^"]*")|(\'[^\']*\')', '#ce9178')
    
    def highlight_pattern(self, pattern, color):
        """Surligne un motif avec une couleur"""
        if isinstance(pattern, list):
            for p in pattern:
                self.highlight_pattern(p, color)
            return
            
        start = '1.0'
        while True:
            pos = self.text_widget.search(pattern, start, stopindex=tk.END, regexp=True)
            if not pos:
                break
            end = self.text_widget.index(f"{pos}+{len(self.text_widget.get(pos, tk.END).split()[0])}c")
            self.text_widget.tag_add(color, pos, end)
            self.text_widget.tag_config(color, foreground=color)
            start = end
    
    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

class RichTextEditor:
    """Éditeur de texte enrichi pour la zone de saisie"""
    
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.setup_tags()
    
    def setup_tags(self):
        """Configure les tags de formatage"""
        # Gras
        self.text_widget.tag_configure("bold", font=('Segoe UI', 11, 'bold'))
        # Italique
        self.text_widget.tag_configure("italic", font=('Segoe UI', 11, 'italic'))
        # Souligné
        self.text_widget.tag_configure("underline", underline=True)
        # Code
        self.text_widget.tag_configure("code", 
                                     background='#f0f0f0', 
                                     foreground='#d63031',
                                     font=('Consolas', 10),
                                     relief='solid', 
                                     borderwidth=1)
    
    def toggle_bold(self):
        """Active/désactive le gras"""
        self.toggle_format("bold")
    
    def toggle_italic(self):
        """Active/désactive l'italique"""
        self.toggle_format("italic")
    
    def toggle_underline(self):
        """Active/désactive le souligné"""
        self.toggle_format("underline")
    
    def toggle_format(self, tag):
        """Active/désactive un format"""
        try:
            current_tags = self.text_widget.tag_names(tk.SEL_FIRST)
            if tag in current_tags:
                self.text_widget.tag_remove(tag, tk.SEL_FIRST, tk.SEL_LAST)
            else:
                self.text_widget.tag_add(tag, tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            # Pas de sélection
            pass
    
    def insert_link(self, url, text=None):
        """Insère un lien"""
        if text is None:
            text = url
        self.text_widget.insert(tk.INSERT, text)
        # Marquer comme lien (visuellement)
        start = self.text_widget.index(tk.INSERT + f"-{len(text)}c")
        end = self.text_widget.index(tk.INSERT)
        self.text_widget.tag_add("link", start, end)
        self.text_widget.tag_configure("link", foreground='#007acc', underline=True)
    
    def insert_code(self, code):
        """Insère du code inline"""
        self.text_widget.insert(tk.INSERT, code)
        start = self.text_widget.index(tk.INSERT + f"-{len(code)}c")
        end = self.text_widget.index(tk.INSERT)
        self.text_widget.tag_add("code", start, end)

class FileHandler:
    """Gestionnaire de fichiers pour les documents"""
    
    @staticmethod
    def extract_text_from_file(file_path):
        """Extrait le texte d'un fichier selon son type"""
        try:
            ext = os.path.splitext(file_path)[1].lower()
            filename = os.path.basename(file_path)
            
            if ext == '.txt':
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    return f"📄 **Document texte ({filename})**\n\n{content}"
            
            elif ext == '.pdf':
                # Essayer d'importer PyPDF2 si disponible
                try:
                    import PyPDF2
                    with open(file_path, 'rb') as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        text = ""
                        for page_num in range(len(pdf_reader.pages)):
                            page = pdf_reader.pages[page_num]
                            text += page.extract_text()
                        return f"📄 **Document PDF ({filename})**\n\n{text}"
                except ImportError:
                    return f"❌ Pour lire les fichiers PDF, installez PyPDF2:\npip install PyPDF2"
                except Exception as e:
                    return f"❌ Erreur lecture PDF: {str(e)}"
            
            elif ext in ['.doc', '.docx']:
                # Essayer d'importer python-docx si disponible
                try:
                    import docx
                    doc = docx.Document(file_path)
                    text = '\n'.join([para.text for para in doc.paragraphs])
                    return f"📄 **Document Word ({filename})**\n\n{text}"
                except ImportError:
                    return f"❌ Pour lire les fichiers Word, installez python-docx:\npip install python-docx"
                except Exception as e:
                    return f"❌ Erreur lecture Word: {str(e)}"
            
            elif ext in ['.xls', '.xlsx']:
                return f"📊 **Fichier Excel ({filename})**\n\n❌ Lecture des fichiers Excel non implémentée. Exportez en CSV ou TXT."
            
            else:
                return f"📁 **Fichier ({filename})**\n\n❌ Format non supporté: {ext}"
                
        except Exception as e:
            return f"❌ Erreur lors de la lecture du fichier: {str(e)}"

class PrometheusAI:
    def __init__(self):
        self.root = tk.Tk()
        self._set_window_icon()
        self.root.title("Prometheus AI - Assistant Local")
        self.root.geometry("1200x700")
        self.root.configure(bg='#f0f0f0')
        
        # Variables optimisées
        self.model = None
        self.model_path = ""
        self.conversations = []
        self.current_conversation = []
        self.current_conversation_id = None
        self.is_loading = False
        self.is_generating = False
        self.stop_generation_flag = False
        self.response_queue = queue.Queue()
        self.loading_progress = 0
        self.current_ai_message_label = None
        self.streaming_text = ""
        self._stream_chunks = []
        self._stream_dirty = False
        self.attached_files = []  # Liste des fichiers attachés
        self.current_streaming_frame = None
        
        # NOUVELLE VARIABLE : garder une référence aux fenêtres de code
        self.code_windows = []
        
        # Gestionnaire de conversations
        self.conv_manager = ConversationManager()
        
        # Configuration des couleurs style ChatGPT (clair)
        self.colors = {
            'user_text': '#000000',
            'bg_primary': '#ffffff',
            'bg_secondary': '#f7f7f8',
            'bg_sidebar': '#202123',
            'accent': '#10a37f',
            'accent_hover': '#0d8c6d',
            'text_primary': '#000000',
            'text_secondary': '#6e6e80',
            'user_bubble': '#10a37f',
            'ai_bubble': '#f7f7f8',
            'border': '#e5e5e5',
            'success': '#10a37f',
            'warning': '#f5a623',
            'error': '#ef4146',
            'sidebar_text': '#ffffff',
            'sidebar_hover': '#2a2b32'
        }
        
        self.setup_ui()
        self.setup_bindings()
        self.check_queue()
        
        # AJOUT : Gestion de l'événement de restauration de fenêtre
        self.root.bind('<Map>', self._on_window_restored)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_window_restored(self, event):
        """Lorsque la fenêtre est restaurée (depuis la barre des tâches)"""
        print("Fenêtre restaurée - rafraîchissement de l'interface...")
        
        # Rafraîchir le canvas de chat
        if hasattr(self, 'chat_canvas'):
            self.chat_canvas.update_idletasks()
        
        # Rafraîchir les fenêtres de code
        for window in self.code_windows:
            try:
                if window.winfo_exists():
                    window.update_idletasks()
            except:
                pass
        
        # Réafficher la fenêtre principale au premier plan
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_close(self):
        """Gestion de la fermeture de l'application"""
        # Fermer toutes les fenêtres de code
        for window in self.code_windows:
            try:
                if window.winfo_exists():
                    window.destroy()
            except:
                pass
        
        # Fermer la fenêtre principale
        self.root.destroy()

    def show_full_code_window(self, code, language="python"):
        """Affiche une fenêtre modale avec le code complet"""
        code_window = tk.Toplevel(self.root)
        code_window.title(f"Code Python complet")
        code_window.geometry("1000x800")
        code_window.configure(bg='#1e1e1e')
        
        # Garder une référence à cette fenêtre
        self.code_windows.append(code_window)
        
        # Gérer la fermeture de la fenêtre
        def on_code_window_close():
            if code_window in self.code_windows:
                self.code_windows.remove(code_window)
            code_window.destroy()
        
        code_window.protocol("WM_DELETE_WINDOW", on_code_window_close)
        
        # Header
        header_frame = tk.Frame(code_window, bg='#2d2d30', height=40)
        header_frame.pack(fill='x', side='top')
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(header_frame, text="CODE PYTHON COMPLET", 
                              bg='#2d2d30', fg='#cccccc', 
                              font=('Consolas', 12, 'bold'))
        title_label.pack(side='left', padx=15)
        
        # Boutons d'action
        button_frame = tk.Frame(header_frame, bg='#2d2d30')
        button_frame.pack(side='right', padx=15)
        
        copy_btn = tk.Button(button_frame, text="📋 Copier tout", 
                           command=lambda: self.copy_to_clipboard(code, code_window),
                           bg='#2d2d30', fg='#cccccc',
                           font=('Segoe UI', 10),
                           relief='flat', bd=0,
                           cursor='hand2')
        copy_btn.pack(side='left', padx=5)
        
        close_btn = tk.Button(button_frame, text="✕ Fermer", 
                            command=on_code_window_close,
                            bg='#2d2d30', fg='#cccccc',
                            font=('Segoe UI', 10),
                            relief='flat', bd=0,
                            cursor='hand2')
        close_btn.pack(side='left', padx=5)
        
        # Cadre principal avec scrollbars
        main_frame = tk.Frame(code_window, bg='#1e1e1e')
        main_frame.pack(fill='both', expand=True, padx=2, pady=2)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(main_frame, orient='vertical')
        h_scrollbar = ttk.Scrollbar(main_frame, orient='horizontal')
        
        # Zone de texte pour le code complet
        code_text = tk.Text(
            main_frame,
            wrap=tk.NONE,  # Pas de retour à la ligne
            bg='#1e1e1e',
            fg='#d4d4d4',
            font=('Consolas', 11),
            insertbackground='#ffffff',
            selectbackground='#264f78',
            relief='flat',
            bd=0,
            padx=20,
            pady=20,
            yscrollcommand=v_scrollbar.set,
            xscrollcommand=h_scrollbar.set
        )
        
        # Configurer les scrollbars
        v_scrollbar.config(command=code_text.yview)
        h_scrollbar.config(command=code_text.xview)
        
        # Packer les éléments
        code_text.pack(side='left', fill='both', expand=True)
        v_scrollbar.pack(side='right', fill='y')
        h_scrollbar.pack(side='bottom', fill='x')
        
        # Insérer le code
        code_text.insert('1.0', code)
        code_text.config(state='disabled')  # Lecture seule
        
        # Appliquer la coloration syntaxique
        self.apply_syntax_highlighting(code_text, language)
        
        # Focus sur la fenêtre
        code_window.focus_set()
        code_window.grab_set()
        
        # AJOUT : Gestion de la restauration pour cette fenêtre aussi
        code_window.bind('<Map>', lambda e: code_window.lift())

    def copy_to_clipboard(self, text, window):
        """Copie le texte dans le presse-papier"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        
        # Afficher une confirmation
        confirm = tk.Label(window, text="✓ Code copié !", 
                         bg='#4caf50', fg='white', 
                         font=('Segoe UI', 10))
        confirm.place(relx=0.5, rely=0.5, anchor='center')
        window.after(1500, confirm.destroy())

    def apply_syntax_highlighting(self, text_widget, language):
        """Applique la coloration syntaxique"""
        text_widget.tag_configure("keyword", foreground='#569cd6')
        text_widget.tag_configure("comment", foreground='#6a9955')
        text_widget.tag_configure("string", foreground='#ce9178')
        text_widget.tag_configure("number", foreground='#b5cea8')
        
        if language == "python":
            python_keywords = ['def', 'class', 'if', 'else', 'elif', 'for', 'while', 
                             'import', 'from', 'as', 'return', 'try', 'except', 
                             'finally', 'with', 'lambda', 'print', 'range', 'len', 
                             'str', 'int', 'float', 'list', 'dict']
            
            # Colorier les keywords
            for keyword in python_keywords:
                start_pos = '1.0'
                while True:
                    start_pos = text_widget.search(r'\b' + keyword + r'\b', start_pos, 
                                                 stopindex=tk.END, regexp=True)
                    if not start_pos:
                        break
                    end_pos = f"{start_pos}+{len(keyword)}c"
                    text_widget.tag_add("keyword", start_pos, end_pos)
                    start_pos = end_pos
            
            # Colorier les commentaires
            start_pos = '1.0'
            while True:
                start_pos = text_widget.search(r'#.*$', start_pos, 
                                             stopindex=tk.END, regexp=True)
                if not start_pos:
                    break
                end_pos = text_widget.index(f"{start_pos} lineend")
                text_widget.tag_add("comment", start_pos, end_pos)
                start_pos = end_pos

    def _resource_path(self, relative: str) -> Path:
        """Retourne le chemin absolu d'une ressource (compatible exe PyInstaller si besoin)."""
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return (base / relative).resolve()

    def _set_window_icon(self):
        """Définit l'icône de la fenêtre (icon.ico)."""
        icon_path = self._resource_path("icon.ico")
        if not icon_path.is_file():
            return

        # Méthode principale (Windows OK avec .ico)
        try:
            self.root.iconbitmap(default=str(icon_path))
            return
        except Exception:
            pass

        # Fallback (Tk parfois capricieux) : iconphoto via PIL
        try:
            img = Image.open(icon_path)
            self._app_icon_imgtk = ImageTk.PhotoImage(img)  # garder une référence !
            self.root.iconphoto(True, self._app_icon_imgtk)
        except Exception:
            pass

    def _on_chat_canvas_configure(self, event):
        """Ajuste la largeur du canvas lors du redimensionnement"""
        if hasattr(self, 'canvas_window'):
            self.chat_canvas.itemconfig(self.canvas_window, width=event.width)
        
    def _resolve_model_file(self, model_name: str) -> Path:
        """Résolution du chemin du modèle"""
        p = Path(model_name)
        if p.is_file():
            return p

        search_paths = [
            Path(__file__).resolve().parent / model_name,
            Path(sys.executable).resolve().parent / model_name,
            Path.cwd() / model_name
        ]
        
        for path in search_paths:
            if path.is_file():
                return path

        return p

    def _prepare_gguf_for_llama(self, model_path: Path) -> Path:
        """Préparation du modèle GGUF"""
        if not model_path.is_file():
            raise FileNotFoundError(f"Fichier modèle introuvable: {model_path}")

        with model_path.open("rb") as f:
            magic = f.read(4)

        if magic == b"GGUF":
            return model_path

        if magic[:2] == b"PK":
            return self._extract_gguf_from_zip(model_path)

        raise ValueError(f"Format de modèle invalide: {magic!r}")

    def _extract_gguf_from_zip(self, model_path: Path) -> Path:
        """Extraction depuis ZIP"""
        try:
            with zipfile.ZipFile(model_path, "r") as zf:
                ggufs = [zi for zi in zf.infolist() 
                        if zi.filename.lower().endswith(".gguf") and zi.file_size > 0]
                
                if not ggufs:
                    raise ValueError("Aucun fichier .gguf dans le ZIP")
                
                ggufs.sort(key=lambda zi: zi.file_size, reverse=True)
                chosen = ggufs[0]
                
                out_path = model_path.parent / f"{model_path.stem}_extracted.gguf"
                
                with zf.open(chosen) as source, open(out_path, 'wb') as target:
                    target.write(source.read())
                
                return out_path

        except zipfile.BadZipFile:
            raise ValueError(f"Archive ZIP invalide: {model_path}")

    def update_progress(self, value, message=""):
        """Met à jour la barre de progression avec pourcentage"""
        self.loading_progress = value
        self.root.after(0, lambda: self.progress_bar.configure(value=value))
        self.root.after(0, lambda: self.progress_label.config(text=f"{value}%"))
        if message:
            self.root.after(0, lambda: self.status_label.config(text=f"● {message} ({value}%)", fg=self.colors['warning']))

    def load_model_thread(self, file_path):
        """Chargement optimisé avec progression"""
        self.is_loading = True
        
        try:
            # Détection automatique des capacités de la machine
            cpu_count = os.cpu_count() or 4
            memory_gb = self.get_system_memory()
            
            # Paramètres adaptatifs selon la machine
            if memory_gb >= 16:
                n_ctx = 8192
                n_threads = min(cpu_count, 8)
                n_batch = 512
                n_gpu_layers = 32 if self.has_gpu() else 0
            elif memory_gb >= 8:
                n_ctx = 4096
                n_threads = min(cpu_count, 6)
                n_batch = 256
                n_gpu_layers = 16 if self.has_gpu() else 0
            else:
                n_ctx = 2048
                n_threads = min(cpu_count, 4)
                n_batch = 128
                n_gpu_layers = 0

            self.update_progress(10, "Analyse du système")
            model_path = self._resolve_model_file(file_path)
            
            self.update_progress(30, "Préparation du modèle")
            gguf_path = self._prepare_gguf_for_llama(model_path)
            
            self.update_progress(50, f"Chargement ({n_threads} threads)")
            
            # Chargement avec paramètres optimisés
            self.model = Llama(
                model_path=str(gguf_path),
                n_ctx=n_ctx,
                n_threads=n_threads,
                n_batch=n_batch,
                n_gpu_layers=n_gpu_layers,
                use_mlock=False,
                use_mmap=True,
                low_vram=True,
                verbose=False
            )
            
            # Progression simulée
            for i in range(60, 101, 10):
                self.update_progress(i, "Optimisation")
                time.sleep(0.1)
            
            self.model_path = file_path
            model_name = os.path.basename(file_path)
            
            self.root.after(0, lambda: self.on_model_loaded(model_name, f"{n_threads} threads, {n_ctx} tokens"))
            
        except Exception as e:
            self.root.after(0, lambda: self.on_model_error(str(e)))
            
    def get_system_memory(self):
        """Estime la mémoire système disponible"""
        try:
            if os.name == 'posix':
                # Linux/Mac
                result = os.popen('free -g').readlines()
                return int(result[1].split()[1])
            elif os.name == 'nt':
                # Windows
                import ctypes
                kernel32 = ctypes.windll.kernel32
                ctypes.windll.kernel32.GetPhysicallyInstalledSystemMemory.restype = ctypes.c_ulonglong
                memory = ctypes.windll.kernel32.GetPhysicallyInstalledSystemMemory()
                return memory // (1024 ** 3)
        except:
            pass
        return 8  # Valeur par défaut

    def has_gpu(self):
        """Vérifie la présence d'un GPU NVIDIA"""
        try:
            result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except:
            return False

    def on_model_loaded(self, model_name, config):
        """Callback de fin de chargement"""
        self.is_loading = False
        self.model_btn.config(state='normal', text="📁 Charger modèle")
        self.model_status.config(text=f"{model_name[:20]}... ({config})")
        self.status_label.config(text="● Prêt", fg=self.colors['success'])
        self.send_btn.config(state='normal', bg=self.colors['accent'])
        self.stop_btn.config(state='disabled')
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()
        messagebox.showinfo("Succès", f"Modèle {model_name} chargé!\n\nConfiguration: {config}")
        
    def on_model_error(self, error):
        """Callback d'erreur"""
        self.is_loading = False
        self.model_btn.config(state='normal', text="📁 Charger modèle")
        self.status_label.config(text="● Erreur de chargement", fg=self.colors['error'])
        self.stop_btn.config(state='disabled')
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()
        messagebox.showerror("Erreur", f"Erreur lors du chargement: {error}")

    def build_prompt(self, user_message):
        """Construction de prompt optimisée"""
        if not self.current_conversation:
            return (f"Tu es Prometheus AI, un assistant IA local spécialisé en programmation.\n"
                   f"L'utilisateur dit: \"{user_message}\"\n\n"
                   f"Si l'utilisateur demande du code Python, réponds UNIQUEMENT avec:\n"
                   f"```python\n[code complet et fonctionnel]\n```\n"
                   f"Ne donne pas d'explications, ne dis pas \"Voici le code\", montre directement le code.")
        
        # Utilise uniquement les 3 derniers échanges pour le contexte
        recent_messages = self.current_conversation[-6:]
        
        prompt = "Historique de la conversation:\n"
        for msg in recent_messages:
            role = "Utilisateur" if msg["role"] == "user" else "Assistant"
            prompt += f"{role}: {msg['content']}\n"
        
        prompt += f"\nUtilisateur: {user_message}\n\n"
        
        # Ajouter une instruction forte pour le code
        if any(keyword in user_message.lower() for keyword in ['python', 'code', 'programme', 'script', 'def ', 'import ']):
            prompt += "Instructions: Fournis UNIQUEMENT le code Python complet entre ```python et ```. Pas d'explications, pas de texte avant ou après."
        
        prompt += "Assistant:"
        return prompt

    def generate_response_streaming(self, user_message):
        """Génération avec streaming - VERSION CORRIGÉE"""
        try:
            self.is_generating = True
            self.stop_generation_flag = False
            prompt = self.build_prompt(user_message)

            # Vérifier si c'est une demande de génération d'image
            if any(keyword in user_message.lower() for keyword in ['génère une image', 'crée une image', 'générer image', 'stable diffusion', 'dall-e']):
                # Réponse honnête sur l'impossibilité
                response = "🎨 **Génération d'images**\n\n"
                response += "❌ **IMPORTANT**: Llama.cpp est un modèle de TEXTE uniquement. Il ne peut PAS générer d'images.\n\n"
                response += "**Pour générer des images, vous avez besoin d'un autre logiciel:**\n"
                response += "1. **Stable Diffusion** (local, gratuit mais 10-20Go)\n"
                response += "2. **DALL-E API** (OpenAI, payant)\n"
                response += "3. **Midjourney** (via Discord, payant)\n\n"
                response += "Je peux vous donner du code Python pour utiliser ces services, mais je ne peux pas générer d'images moi-même."
                self.response_queue.put(("stream_end", response))
                self.is_generating = False
                return

            response = self.model.create_completion(
                prompt,
                max_tokens=4096,  # Augmenté pour plus de code
                temperature=0.2,
                top_p=0.9,
                top_k=40,
                repeat_penalty=1.1,
                stream=True,
                stop=["\n\nUtilisateur:", "###", "```\n```", "```\n\n```"]
            )

            full_response = ""

            for chunk in response:
                # Vérifier si l'utilisateur a demandé d'arrêter
                if self.stop_generation_flag:
                    self.response_queue.put(("error", "Génération arrêtée par l'utilisateur"))
                    break
                
                token = ""

                if isinstance(chunk, dict):
                    choices = chunk.get("choices") or []
                    if choices and isinstance(choices[0], dict):
                        token = choices[0].get("text", "") or ""

                elif hasattr(chunk, "choices") and chunk.choices:
                    c0 = chunk.choices[0]
                    if isinstance(c0, dict):
                        token = c0.get("text", "") or ""
                    elif hasattr(c0, "text"):
                        token = c0.text or ""

                if token:
                    full_response += token
                    self.response_queue.put(("stream_token", token))

            if not self.stop_generation_flag:
                ai_response = full_response.strip()
                ai_response = self.format_code_response(ai_response, user_message)

                if ai_response and not self.is_duplicate_response(ai_response):
                    self.current_conversation.append({
                        "role": "assistant",
                        "content": ai_response,
                        "timestamp": datetime.now().isoformat()
                    })

                    self.save_conversation()
                    self.response_queue.put(("stream_end", ai_response))
                else:
                    # CORRECTION : Utiliser generate_statistics_code au lieu de generate_default_code
                    default_code = self.generate_statistics_code(user_message)
                    self.current_conversation.append({
                        "role": "assistant",
                        "content": default_code,
                        "timestamp": datetime.now().isoformat()
                    })
                    self.save_conversation()
                    self.response_queue.put(("stream_end", default_code))
            
            self.is_generating = False
            self.stop_generation_flag = False

        except Exception as e:
            error_msg = f"Erreur lors de la génération: {str(e)}"
            print(f"DEBUG - Erreur génération: {error_msg}")
            self.response_queue.put(("error", error_msg))
            self.is_generating = False
            self.stop_generation_flag = False

    def format_code_response(self, response, user_message):
        """Formate correctement la réponse pour afficher du code Python - CORRIGÉ"""
        response = response.strip()
        
        if any(keyword in user_message.lower() for keyword in ['python', 'code', 'programme', 'script', 'statistique', 'statistiques']):
            # Recherche améliorée des blocs de code
            if '```python' in response:
                # Extraire tout ce qui se trouve entre ```python et le prochain ```
                pattern = r'```python\s*(.*?)\s*```'
                matches = re.findall(pattern, response, re.DOTALL)
                if matches:
                    code = matches[0].strip()
                    return f"```python\n{code}\n```"
            
            # Si pas de backticks mais que ça ressemble à du code Python
            elif self.looks_like_python_code(response):
                return f"```python\n{response}\n```"
            
            else:
                # Générer un exemple de statistiques
                return self.generate_statistics_code(user_message)
        
        return response

    def generate_statistics_code(self, user_message):
        """Génère un code complet pour les statistiques"""
        return """```python
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# =============================================
# PROGRAMME COMPLET POUR LES STATISTIQUES AVANCÉES
# =============================================

class AnalyseStatistiques:
    '''Classe pour effectuer des analyses statistiques complètes'''
    
    def __init__(self, data=None, fichier=None):
        '''
        Initialise l'analyse statistique
        
        Parameters:
        -----------
        data : DataFrame ou dict, optionnel
            Données à analyser
        fichier : str, optionnel
            Chemin vers un fichier CSV, Excel ou JSON
        '''
        if fichier:
            self.charger_donnees(fichier)
        elif data is not None:
            if isinstance(data, pd.DataFrame):
                self.data = data
            else:
                self.data = pd.DataFrame(data)
        else:
            self.data = pd.DataFrame()
            
        self.resultats = {}
    
    def charger_donnees(self, fichier):
        '''Charge les données depuis un fichier'''
        extension = fichier.split('.')[-1].lower()
        
        try:
            if extension == 'csv':
                self.data = pd.read_csv(fichier)
            elif extension in ['xls', 'xlsx']:
                self.data = pd.read_excel(fichier)
            elif extension == 'json':
                self.data = pd.read_json(fichier)
            else:
                raise ValueError(f"Format non supporté: {extension}")
                
            print(f"✅ Données chargées: {self.data.shape[0]} lignes, {self.data.shape[1]} colonnes")
        except Exception as e:
            print(f"❌ Erreur de chargement: {e}")
            self.data = pd.DataFrame()
    
    def resume_complet(self):
        '''Génère un résumé complet des données'''
        if self.data.empty:
            print("❌ Aucune donnée à analyser")
            return
        
        print("=" * 60)
        print("📊 RÉSUMÉ COMPLET DES DONNÉES")
        print("=" * 60)
        
        # Informations basiques
        print(f"\n📋 Dimensions: {self.data.shape[0]} lignes × {self.data.shape[1]} colonnes")
        print(f"📅 Période: {self.data.index.min()} à {self.data.index.max()}" 
              if hasattr(self.data.index, 'min') else "📅 Période: Non spécifiée")
        
        # Types de données
        print("\n🎯 TYPES DE DONNÉES:")
        print(self.data.dtypes)
        
        # Statistiques descriptives
        print("\n📈 STATISTIQUES DESCRIPTIVES:")
        print(self.data.describe(include='all'))
        
        # Valeurs manquantes
        valeurs_manquantes = self.data.isnull().sum()
        if valeurs_manquantes.any():
            print(f"\n⚠️  VALEURS MANQUANTES:")
            for col, nb in valeurs_manquantes[valeurs_manquantes > 0].items():
                pourcentage = (nb / len(self.data)) * 100
                print(f"  {col}: {nb} valeurs ({pourcentage:.1f}%)")
        
        # Valeurs uniques
        print("\n🔍 VALEURS UNIQUES (top 5 par colonne):")
        for col in self.data.columns:
            if self.data[col].dtype == 'object' or self.data[col].nunique() < 10:
                uniques = self.data[col].unique()[:5]
                print(f"  {col}: {len(uniques)} valeurs uniques → {uniques}")
    
    def analyse_exploratoire(self):
        '''Effectue une analyse exploratoire des données'''
        if self.data.empty:
            return
        
        print("\n" + "=" * 60)
        print("🔎 ANALYSE EXPLORATOIRE")
        print("=" * 60)
        
        # Corrélations
        if len(self.data.select_dtypes(include=[np.number]).columns) > 1:
            correlations = self.data.corr(numeric_only=True)
            print("\n📊 MATRICE DE CORRÉLATION:")
            print(correlations)
            
            # Corrélations fortes
            strong_corr = []
            for i in range(len(correlations.columns)):
                for j in range(i+1, len(correlations.columns)):
                    if abs(correlations.iloc[i, j]) > 0.7:
                        strong_corr.append((
                            correlations.columns[i],
                            correlations.columns[j],
                            correlations.iloc[i, j]
                        ))
            
            if strong_corr:
                print("\n🔗 CORRÉLATIONS FORTES (|r| > 0.7):")
                for var1, var2, corr in strong_corr:
                    print(f"  {var1} ↔ {var2}: {corr:.3f}")
        
        # Distributions
        print("\n📏 DISTRIBUTIONS:")
        numeric_cols = self.data.select_dtypes(include=[np.number]).columns
        for col in numeric_cols[:5]:  # Limite aux 5 premières colonnes
            skewness = self.data[col].skew()
            kurtosis = self.data[col].kurtosis()
            
            distribution_type = "Normale"
            if abs(skewness) > 1:
                distribution_type = "Asymétrique"
            if abs(kurtosis) > 3:
                distribution_type += " à queue épaisse"
            
            print(f"  {col}: Skewness={skewness:.2f}, Kurtosis={kurtosis:.2f} → {distribution_type}")
    
    def tests_statistiques(self):
        '''Effectue des tests statistiques'''
        if self.data.empty:
            return
        
        numeric_cols = self.data.select_dtypes(include=[np.number]).columns.tolist()
        
        if len(numeric_cols) >= 2:
            print("\n" + "=" * 60)
            print("🧪 TESTS STATISTIQUES")
            print("=" * 60)
            
            # Test de normalité (Shapiro-Wilk)
            print("\n📊 TEST DE NORMALITÉ (Shapiro-Wilk):")
            for col in numeric_cols[:3]:  # Limite aux 3 premières colonnes
                data_clean = self.data[col].dropna()
                if len(data_clean) >= 3 and len(data_clean) <= 5000:
                    stat, p_value = stats.shapiro(data_clean)
                    normal = "Normal" if p_value > 0.05 else "Non-normal"
                    print(f"  {col}: W={stat:.3f}, p={p_value:.3e} → {normal}")
            
            # Test T pour échantillons indépendants
            if len(numeric_cols) >= 2:
                print("\n📈 TEST T (échantillons indépendants):")
                col1, col2 = numeric_cols[0], numeric_cols[1]
                t_stat, p_value = stats.ttest_ind(
                    self.data[col1].dropna(),
                    self.data[col2].dropna(),
                    nan_policy='omit'
                )
                difference = "Différence significative" if p_value < 0.05 else "Pas de différence significative"
                print(f"  {col1} vs {col2}: t={t_stat:.3f}, p={p_value:.3e} → {difference}")
    
    def visualisations(self, save=False):
        '''Génère des visualisations'''
        if self.data.empty:
            return
        
        numeric_cols = self.data.select_dtypes(include=[np.number]).columns.tolist()
        categoric_cols = self.data.select_dtypes(include=['object', 'category']).columns.tolist()
        
        print("\n" + "=" * 60)
        print("🎨 GÉNÉRATION DE VISUALISATIONS")
        print("=" * 60)
        
        # Configuration du style
        plt.style.use('seaborn-v0_8-darkgrid')
        sns.set_palette("husl")
        
        # 1. Histogrammes
        if numeric_cols:
            fig, axes = plt.subplots(1, min(3, len(numeric_cols)), figsize=(15, 4))
            axes = axes if isinstance(axes, np.ndarray) else [axes]
            
            for idx, col in enumerate(numeric_cols[:3]):
                ax = axes[idx]
                self.data[col].hist(ax=ax, bins=30, edgecolor='black')
                ax.set_title(f'Distribution de {col}')
                ax.set_xlabel(col)
                ax.set_ylabel('Fréquence')
            
            plt.tight_layout()
            if save:
                plt.savefig('histogrammes.png', dpi=300, bbox_inches='tight')
            plt.show()
        
        # 2. Boxplots
        if numeric_cols:
            fig, axes = plt.subplots(1, min(3, len(numeric_cols)), figsize=(15, 4))
            axes = axes if isinstance(axes, np.ndarray) else [axes]
            
            for idx, col in enumerate(numeric_cols[:3]):
                ax = axes[idx]
                ax.boxplot(self.data[col].dropna())
                ax.set_title(f'Boxplot de {col}')
                ax.set_ylabel(col)
            
            plt.tight_layout()
            if save:
                plt.savefig('boxplots.png', dpi=300, bbox_inches='tight')
            plt.show()
        
        # 3. Matrice de corrélation (heatmap)
        if len(numeric_cols) > 1:
            corr_matrix = self.data[numeric_cols].corr()
            
            plt.figure(figsize=(10, 8))
            sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0,
                       square=True, linewidths=1, cbar_kws={"shrink": 0.8})
            plt.title('Matrice de Corrélation', fontsize=16, pad=20)
            plt.tight_layout()
            if save:
                plt.savefig('correlation_heatmap.png', dpi=300, bbox_inches='tight')
            plt.show()
        
        # 4. Scatter plot si au moins 2 variables numériques
        if len(numeric_cols) >= 2:
            plt.figure(figsize=(10, 6))
            plt.scatter(self.data[numeric_cols[0]], self.data[numeric_cols[1]],
                       alpha=0.6, edgecolors='w', s=50)
            
            # Régression linéaire
            x = self.data[numeric_cols[0]].dropna()
            y = self.data[numeric_cols[1]].dropna()
            if len(x) == len(y) and len(x) > 1:
                slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
                plt.plot(x, intercept + slope*x, 'r-', linewidth=2,
                        label=f'Régression: r={r_value:.3f}, p={p_value:.3e}')
                plt.legend()
            
            plt.xlabel(numeric_cols[0])
            plt.ylabel(numeric_cols[1])
            plt.title(f'Relation entre {numeric_cols[0]} et {numeric_cols[1]}', fontsize=14)
            plt.grid(True, alpha=0.3)
            
            if save:
                plt.savefig('scatter_plot.png', dpi=300, bbox_inches='tight')
            plt.show()
    
    def rapport_complet(self, fichier_sortie='rapport_statistiques.txt'):
        '''Génère un rapport complet des analyses'''
        import io
        
        # Capture de la sortie
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()
        
        try:
            # Exécute toutes les analyses
            self.resume_complet()
            self.analyse_exploratoire()
            self.tests_statistiques()
            
            # Sauvegarde le rapport
            with open(fichier_sortie, 'w', encoding='utf-8') as f:
                f.write(buffer.getvalue())
            
            print(f"\n✅ Rapport sauvegardé dans: {fichier_sortie}")
            
        finally:
            sys.stdout = old_stdout
        
        # Affiche le rapport
        print(buffer.getvalue())

# =============================================
# EXEMPLE D'UTILISATION
# =============================================
if __name__ == "__main__":
    print("=" * 60)
    print("📊 ANALYSE STATISTIQUE AVANCÉE - PROMETHEUS AI")
    print("=" * 60)
    
    # Option 1: Données d'exemple
    donnees_exemple = {
        'Age': [25, 30, 35, 40, 45, 50, 55, 60, 65, 70],
        'Salaire': [30000, 35000, 40000, 45000, 50000, 55000, 60000, 65000, 70000, 75000],
        'Experience': [1, 3, 5, 7, 9, 11, 13, 15, 17, 19],
        'Genre': ['M', 'F', 'M', 'F', 'M', 'F', 'M', 'F', 'M', 'F'],
        'Satisfaction': [3, 4, 5, 4, 3, 5, 4, 3, 5, 4]
    }
    
    # Option 2: Charger depuis un fichier
    # analyse = AnalyseStatistiques(fichier='donnees.csv')
    
    # Création de l'analyseur
    analyse = AnalyseStatistiques(data=donnees_exemple)
    
    # Exécution des analyses
    analyse.rapport_complet()
    
    # Génération des visualisations
    print("\n🎨 Génération des graphiques...")
    analyse.visualisations(save=True)
    
    print("\n" + "=" * 60)
    print("✅ ANALYSE TERMINÉE AVEC SUCCÈS!")
    print("=" * 60)
    
    # Suggestions d'analyses supplémentaires
    print("\n💡 SUGGESTIONS D'ANALYSES SUPPLÉMENTAIRES:")
    print("  1. Analyse de variance (ANOVA)")
    print("  2. Régression linéaire multiple")
    print("  3. Analyse en composantes principales (PCA)")
    print("  4. Clustering (K-means, DBSCAN)")
    print("  5. Séries temporelles (ARIMA, Prophet)")
    
    # Commandes pour installer les dépendances manquantes
    print("\n📦 INSTALLATION DES DÉPENDANCES:")
    print("  pip install numpy pandas matplotlib seaborn scipy scikit-learn")
    
    print("\n" + "=" * 60)
    print("🔧 FONCTIONNALITÉS IMPLÉMENTÉES:")
    print("  • Chargement de données (CSV, Excel, JSON)")
    print("  • Analyse descriptive complète")
    print("  • Tests statistiques (normalité, test-t)")
    print("  • Visualisations (histogrammes, boxplots, scatter plots)")
    print("  • Génération de rapport automatique")
    print("  • Gestion des valeurs manquantes")
    print("  • Détection des corrélations")
    print("=" * 60)
```"""

    def generate_default_code(self, user_message):
        """Génère un code Python par défaut quand aucune réponse n'est générée"""
        return f"""```python
# Programme Python généré par Prometheus AI
# Question de l'utilisateur : {user_message[:50]}...

print("Bonjour ! Voici un programme Python de base.")

def exemple_fonction():
    '''Exemple de fonction Python'''
    print("Cette fonction est un exemple.")
    return 42

if __name__ == "__main__":
    resultat = exemple_fonction()
    print(f"Résultat : {{resultat}}")
    
# Note : Pour des programmes plus spécifiques, 
# précisez votre demande (ex: "écris un programme pour calculer la factorielle")
```"""

    def looks_like_python_code(self, text):
        """Détermine si le texte ressemble à du code Python"""
        python_indicators = [
            'import ', 'def ', 'class ', 'print(', 'return ', 'if __name__',
            'from ', 'as ', 'try:', 'except ', 'finally:', 'with ', 'lambda ',
            'for ', 'while ', 'if ', 'elif ', 'else:', 'and ', 'or ', 'not ',
            'True', 'False', 'None', 'self.', 'super()'
        ]
        
        lines = text.strip().split('\n')
        if len(lines) < 2:
            return False
            
        code_like_lines = 0
        for line in lines:
            line_clean = line.strip()
            if any(indicator in line_clean for indicator in python_indicators):
                code_like_lines += 1
            elif line_clean and not line_clean.startswith('#') and len(line_clean) > 3:
                code_like_lines += 0.5
        
        return code_like_lines >= 2

    def is_duplicate_response(self, new_response):
        """Vérifie si la nouvelle réponse est un doublon de la dernière réponse"""
        if not self.current_conversation:
            return False
        
        ai_messages = [msg for msg in self.current_conversation if msg["role"] == "assistant"]
        if not ai_messages:
            return False
            
        last_ai_response = ai_messages[-1]["content"]
        return last_ai_response.strip().lower() == new_response.strip().lower()

    def setup_ui(self):
        """Interface style ChatGPT"""
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
        self.setup_sidebar()
        self.setup_main_area()
        
    def setup_sidebar(self):
        """Sidebar style ChatGPT"""
        sidebar = tk.Frame(self.root, bg=self.colors['bg_sidebar'], width=260)
        sidebar.grid(row=0, column=0, sticky='nsew')
        sidebar.grid_propagate(False)
        
        # En-tête
        header_frame = tk.Frame(sidebar, bg=self.colors['bg_sidebar'])
        header_frame.pack(fill='x', padx=15, pady=15)
        
        title = tk.Label(header_frame, text="Prometheus AI", 
                        bg=self.colors['bg_sidebar'], fg=self.colors['sidebar_text'],
                        font=('Segoe UI', 16, 'bold'))
        title.pack(anchor='w')
        
        # BOUTON DE DONATION PAYPAL
        paypal_frame = tk.Frame(sidebar, bg=self.colors['bg_sidebar'])
        paypal_frame.pack(fill='x', padx=15, pady=(0, 10))
        
        paypal_btn = tk.Button(paypal_frame, text="❤️ Faire un don (PayPal)",
                             bg='#FFC439', fg='#003087',
                             command=self.open_paypal_donation,
                             font=('Segoe UI', 10, 'bold'),
                             relief='flat', height=1,
                             cursor='hand2')
        paypal_btn.pack(fill='x', pady=(0, 8))
        
        # Bouton nouvelle conversation
        new_chat_btn = tk.Button(sidebar, text="+ Nouvelle discussion",
                               bg=self.colors['accent'], fg='white',
                               command=self.new_conversation,
                               font=('Segoe UI', 11),
                               relief='flat', height=1,
                               cursor='hand2')
        new_chat_btn.pack(fill='x', padx=15, pady=(0, 8))
        
        # Liste des conversations
        conversations_frame = tk.Frame(sidebar, bg=self.colors['bg_sidebar'])
        conversations_frame.pack(fill='both', expand=True, padx=0, pady=0)
        
        # Scrollbar pour la liste des conversations
        conv_scrollbar = ttk.Scrollbar(conversations_frame)
        conv_scrollbar.pack(side='right', fill='y')
        
        self.conversations_list = tk.Listbox(conversations_frame,
                                           bg=self.colors['sidebar_hover'],
                                           fg=self.colors['sidebar_text'],
                                           selectbackground=self.colors['accent'],
                                           borderwidth=0,
                                           highlightthickness=0,
                                           font=('Segoe UI', 10),
                                           cursor='hand2',
                                           yscrollcommand=conv_scrollbar.set)
        self.conversations_list.pack(fill='both', expand=True, padx=15, pady=8)
        conv_scrollbar.config(command=self.conversations_list.yview)
        
        # Menu contextuel pour supprimer les conversations
        self.conv_context_menu = tk.Menu(self.root, tearoff=0, bg='white', fg='black')
        self.conv_context_menu.add_command(label="Supprimer", command=self.delete_conversation)
        self.conversations_list.bind("<Button-3>", self.show_conv_context_menu)
        
        # Section modèle
        model_frame = tk.Frame(sidebar, bg=self.colors['bg_sidebar'])
        model_frame.pack(fill='x', padx=15, pady=15)
        
        self.model_btn = tk.Button(model_frame, text="📁 Charger modèle GGUF",
                                 bg=self.colors['sidebar_hover'], fg=self.colors['sidebar_text'],
                                 command=self.load_model_dialog,
                                 font=('Segoe UI', 10),
                                 relief='flat',
                                 cursor='hand2')
        self.model_btn.pack(fill='x')
        
        # Barre de progression
        progress_container = tk.Frame(model_frame, bg=self.colors['bg_sidebar'])
        progress_container.pack(fill='x', pady=(8, 0))
        
        self.progress_bar = ttk.Progressbar(progress_container, 
                                          orient='horizontal',
                                          mode='determinate')
        self.progress_bar.pack(side='left', fill='x', expand=True)
        
        self.progress_label = tk.Label(progress_container, text="0%",
                                     bg=self.colors['bg_sidebar'], fg=self.colors['sidebar_text'],
                                     font=('Segoe UI', 8), width=4)
        self.progress_label.pack(side='right', padx=(5, 0))
        
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()
        
        self.model_status = tk.Label(model_frame, text="Aucun modèle chargé",
                                   bg=self.colors['bg_sidebar'], fg=self.colors['text_secondary'],
                                   font=('Segoe UI', 9))
        self.model_status.pack(anchor='w', pady=(5, 0))
        
        # Charger les conversations sauvegardées
        self.load_conversations()

    def open_paypal_donation(self):
        """Ouvre le lien de donation PayPal"""
        import webbrowser
        webbrowser.open("https://www.paypal.com/donate/?hosted_button_id=FSX7RHUT4BDRY")
        
    def setup_main_area(self):
        """Zone principale style ChatGPT"""
        main_frame = tk.Frame(self.root, bg=self.colors['bg_primary'])
        main_frame.grid(row=0, column=1, sticky='nsew')
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)
        
        # Barre de titre
        title_frame = tk.Frame(main_frame, bg=self.colors['bg_primary'], height=50)
        title_frame.grid(row=0, column=0, sticky='ew', padx=20, pady=10)
        title_frame.grid_propagate(False)
        
        self.conv_title = tk.Label(title_frame, text="Nouvelle discussion", 
                                 bg=self.colors['bg_primary'], fg=self.colors['text_primary'],
                                 font=('Segoe UI', 14, 'bold'))
        self.conv_title.pack(side='left')
        
        # Boutons d'action
        btn_frame = tk.Frame(title_frame, bg=self.colors['bg_primary'])
        btn_frame.pack(side='right')
        
        # Bouton donation PayPal (en haut à droite)
        paypal_btn_main = tk.Button(btn_frame, text="❤️ Donation",
                                  command=self.open_paypal_donation,
                                  bg=self.colors['bg_primary'], fg='#FFC439',
                                  font=('Segoe UI', 9, 'bold'),
                                  relief='flat',
                                  cursor='hand2')
        paypal_btn_main.pack(side='left', padx=(5, 10))
        
        self.copy_btn = tk.Button(btn_frame, text="📋 Copier",
                                command=self.copy_conversation,
                                bg=self.colors['bg_primary'], fg=self.colors['text_secondary'],
                                font=('Segoe UI', 9),
                                relief='flat',
                                cursor='hand2')
        self.copy_btn.pack(side='left', padx=(5, 0))
        
        self.clear_btn = tk.Button(btn_frame, text="🗑️ Effacer",
                                 command=self.clear_conversation,
                                 bg=self.colors['bg_primary'], fg=self.colors['error'],
                                 font=('Segoe UI', 9),
                                 relief='flat',
                                 cursor='hand2')
        self.clear_btn.pack(side='left', padx=(5, 0))
        
        self.status_label = tk.Label(title_frame, text="● Prêt", 
                                   bg=self.colors['bg_primary'], fg=self.colors['success'],
                                   font=('Segoe UI', 9))
        self.status_label.pack(side='right', padx=(10, 0))
        
        # Zone de chat
        self.setup_chat_area(main_frame)
        
        # Zone de saisie avec outils
        self.setup_input_area(main_frame)
        
    def setup_chat_area(self, parent):
        """Zone de conversation"""
        chat_frame = tk.Frame(parent, bg=self.colors['bg_primary'])
        chat_frame.grid(row=1, column=0, sticky='nsew', padx=0, pady=0)
        
        # Canvas avec scrollbar
        self.chat_canvas = tk.Canvas(chat_frame, bg=self.colors['bg_primary'],
                                   highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(chat_frame, orient="vertical", 
                                command=self.chat_canvas.yview)
        
        self.scrollable_frame = tk.Frame(self.chat_canvas, bg=self.colors['bg_primary'])
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.chat_canvas.configure(
                scrollregion=self.chat_canvas.bbox("all")
            )
        )
        
        self.canvas_window = self.chat_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.chat_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.chat_canvas.pack(side="left", fill="both", expand=True, padx=20)
        scrollbar.pack(side="right", fill="y")
        
        self.chat_canvas.bind("<Configure>", self._on_chat_canvas_configure)
        self.chat_canvas.bind("<MouseWheel>", self._on_mousewheel)
        
        # Message de bienvenue
        self.show_welcome_message()
        
    def show_welcome_message(self):
        """Affiche un message de bienvenue"""
        welcome_frame = tk.Frame(self.scrollable_frame, bg=self.colors['bg_primary'])
        welcome_frame.pack(fill='x', padx=20, pady=20)
        
        welcome_label = tk.Label(welcome_frame, 
                               text="👋 **Prometheus AI - Assistant Local**\n\n"
                               "**Capacités:**\n"
                               "• Charger des modèles GGUF (texte uniquement)\n"
                               "• Générer du code Python\n"
                               "• Répondre à des questions générales\n"
                               "• Joindre des images (aperçu seulement)\n"
                               "• Lire des documents texte simples\n\n"
                               "**LIMITATIONS:**\n"
                               "❌ Ne peut PAS générer d'images\n"
                               "❌ Ne peut PAS analyser le contenu d'images\n"
                               "❌ Ne peut lire que les fichiers texte simples\n\n"
                               "Exemple: \"écris un programme Python pour vérifier si un nombre est premier\"",
                               bg=self.colors['bg_primary'], fg=self.colors['text_secondary'],
                               font=('Segoe UI', 11),
                               justify='left',
                               wraplength=600)
        welcome_label.pack(expand=True)
        
    def setup_input_area(self, parent):
        """Zone de saisie avec outils de formatage"""
        input_frame = tk.Frame(parent, bg=self.colors['bg_primary'])
        input_frame.grid(row=2, column=0, sticky='ew', padx=20, pady=20)
        
        # Barre d'outils en bas
        toolbar_frame = tk.Frame(input_frame, bg=self.colors['bg_primary'])
        toolbar_frame.pack(fill='x', pady=(0, 10))
        
        # Boutons d'outils
        self.attach_btn = tk.Button(toolbar_frame, text="📎 Joindre un fichier",
                                  command=self.attach_file,
                                  bg=self.colors['bg_primary'], fg=self.colors['text_secondary'],
                                  font=('Segoe UI', 9),
                                  relief='flat',
                                  cursor='hand2')
        self.attach_btn.pack(side='left')
        
        # Afficher le nom du fichier attaché
        self.attach_label = tk.Label(toolbar_frame, text="",
                                   bg=self.colors['bg_primary'], fg=self.colors['accent'],
                                   font=('Segoe UI', 9))
        self.attach_label.pack(side='left', padx=(10, 0))
        
        input_container = tk.Frame(input_frame, bg=self.colors['border'], 
                                 relief='flat', bd=1)
        input_container.pack(fill='x')
        
        # Zone de texte sans limite de caractères
        self.input_text = tk.Text(input_container, 
                                height=3,
                                bg=self.colors['bg_primary'],
                                fg=self.colors['text_primary'],
                                font=('Segoe UI', 11),
                                relief='flat',
                                borderwidth=0,
                                padx=15, pady=12,
                                wrap=tk.WORD)
        
        # Initialiser l'éditeur de texte enrichi
        self.rich_editor = RichTextEditor(self.input_text)
        
        # Scrollbar pour la zone de texte
        text_scrollbar = ttk.Scrollbar(input_container, orient="vertical", command=self.input_text.yview)
        self.input_text.configure(yscrollcommand=text_scrollbar.set)
        
        self.input_text.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        text_scrollbar.pack(side="right", fill="y")
        
        # Bouton d'envoi et bouton Stop
        btn_frame = tk.Frame(input_frame, bg=self.colors['bg_primary'])
        btn_frame.pack(fill='x', pady=(10, 0))
        
        self.send_btn = tk.Button(btn_frame, text="Envoyer", 
                                command=self.send_message,
                                bg=self.colors['accent'], fg='white',
                                font=('Segoe UI', 10, 'bold'),
                                relief='flat', height=1, width=8,
                                state='disabled',
                                cursor='hand2')
        self.send_btn.pack(side='right')
        
        # Bouton Stop
        self.stop_btn = tk.Button(btn_frame, text="Stop", 
                                command=self.stop_generation,
                                bg=self.colors['error'], fg='white',
                                font=('Segoe UI', 10, 'bold'),
                                relief='flat', height=1, width=6,
                                state='disabled',
                                cursor='hand2')
        self.stop_btn.pack(side='right', padx=(5, 0))
        
        self.typing_label = tk.Label(btn_frame, text="",
                                   bg=self.colors['bg_primary'], fg=self.colors['text_secondary'],
                                   font=('Segoe UI', 9))
        self.typing_label.pack(side='left')
        
    def stop_generation(self):
        """Arrête la génération en cours"""
        if self.is_generating:
            self.stop_generation_flag = True
            self.is_generating = False
            self.status_label.config(text="● Génération arrêtée", fg=self.colors['error'])
            self.send_btn.config(state='normal', bg=self.colors['accent_hover'])
            self.stop_btn.config(state='disabled')
        
    def setup_bindings(self):
        """Configuration des raccourcis"""
        self.root.bind('<Return>', self.on_enter_key)
        self.root.bind('<Control-Return>', lambda e: self.input_text.insert(tk.END, '\n'))
        self.conversations_list.bind('<<ListboxSelect>>', self.load_conversation)
        self.input_text.bind('<KeyRelease>', self.on_input_change)
        
    def on_enter_key(self, event):
        """Gestion de la touche Entrée"""
        if event.state == 0:  # Entrée seule (sans Ctrl)
            self.send_message()
            return "break"  # Empêche l'ajout de nouvelle ligne
        return None
        
    def on_input_change(self, event=None):
        """Gestion des changements de saisie"""
        text = self.input_text.get("1.0", "end-1c").strip()
        if self.model and text and not self.is_generating:
            self.send_btn.config(state='normal', bg=self.colors['accent_hover'])
            self.typing_label.config(text=f"{len(text)} caractères")
        else:
            self.send_btn.config(state='disabled', bg=self.colors['accent'])
            self.typing_label.config(text="")
        
    def _on_mousewheel(self, event):
        """Scroll avec molette"""
        self.chat_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
    def check_queue(self):
        """Vérification queue + streaming fluide"""
        try:
            while True:
                message_type, data = self.response_queue.get_nowait()

                if message_type == "stream_token":
                    self._stream_chunks.append(data)
                    self._stream_dirty = True

                elif message_type == "stream_end":
                    if self._stream_dirty:
                        self.streaming_text += "".join(self._stream_chunks)
                        self._stream_chunks.clear()
                        self._stream_dirty = False
                        self.update_streaming_message(self.streaming_text)

                    self.finalize_streaming_message(data)
                    self.status_label.config(text="● Prêt", fg=self.colors['success'])
                    self.send_btn.config(state='normal', bg=self.colors['accent_hover'])
                    self.stop_btn.config(state='disabled')

                elif message_type == "error":
                    self.display_error_message(data)
                    self.status_label.config(text="● Erreur", fg=self.colors['error'])
                    self.send_btn.config(state='normal', bg=self.colors['accent_hover'])
                    self.stop_btn.config(state='disabled')

        except queue.Empty:
            pass
        finally:
            if self._stream_dirty and self.current_ai_message_label and self.current_ai_message_label.winfo_exists():
                self.streaming_text += "".join(self._stream_chunks)
                self._stream_chunks.clear()
                self._stream_dirty = False
                self.update_streaming_message(self.streaming_text)

            self.root.after(33, self.check_queue)
    
    def attach_file(self):
        """Joindre un fichier (image ou document)"""
        file_path = filedialog.askopenfilename(
            title="Sélectionner un fichier",
            filetypes=[
                ("Tous les fichiers", "*.*"),
                ("Images", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("Documents texte", "*.txt"),
                ("PDF", "*.pdf"),
                ("Word", "*.doc *.docx"),
                ("Excel", "*.xls *.xlsx")
            ]
        )
        if file_path:
            self.attached_files.append(file_path)
            filename = os.path.basename(file_path)
            
            # Afficher le fichier dans le chat
            self.display_file_preview(file_path)
            
            # Mettre à jour le label
            self.attach_label.config(text=f"📎 {filename}")
            
            # Traiter le fichier selon son type
            ext = os.path.splitext(file_path)[1].lower()
            
            if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                message = f"🖼️ **Image jointe:** {filename}\n\n"
                message += "ℹ️ **Note importante:** Llama.cpp ne peut PAS analyser le contenu des images.\n"
                message += "Pour analyser des images, vous avez besoin d'un modèle 'vision' comme LLaVA.\n"
                message += "Je peux seulement afficher un aperçu de l'image."
            
            elif ext in ['.txt', '.pdf', '.doc', '.docx']:
                # Extraire le texte
                extracted = FileHandler.extract_text_from_file(file_path)
                message = extracted
                
                # Si c'est du texte, le stocker pour référence
                if ext == '.txt' and not extracted.startswith("❌"):
                    self.last_extracted_text = extracted
            else:
                message = f"📁 **Fichier joint:** {filename}\n\n"
                message += f"Type de fichier: {ext}\n"
                message += "Je ne peux pas lire ce type de fichier."
            
            # Afficher le message dans le chat
            self.display_user_message(message)
    
    def display_file_preview(self, file_path):
        """Affiche un aperçu du fichier dans le chat"""
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path) / 1024  # KB
        
        ext = os.path.splitext(file_path)[1].lower()
        
        file_frame = tk.Frame(self.scrollable_frame, bg=self.colors['bg_primary'])
        file_frame.pack(fill='x', padx=20, pady=8)
        
        avatar_frame = tk.Frame(file_frame, bg=self.colors['bg_primary'])
        avatar_frame.pack(anchor='w', side='left')
        
        avatar = tk.Label(avatar_frame, text="👤",
                        bg=self.colors['bg_primary'], fg=self.colors['user_text'],
                        font=('Segoe UI', 12))
        avatar.pack(padx=(0, 12))
        
        file_container = tk.Frame(file_frame, bg=self.colors['bg_primary'], relief='solid', bd=1)
        file_container.pack(anchor='w', side='left')
        
        # Pour les images, afficher un aperçu
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
            try:
                img = Image.open(file_path)
                img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                
                img_label = tk.Label(file_container, image=img_tk, bg='white')
                img_label.image = img_tk
                img_label.pack(padx=10, pady=10)
            except Exception as e:
                print(f"Erreur affichage image: {e}")
        
        file_info = tk.Label(file_container, 
                          text=f"📎 {filename}\nTaille: {file_size:.1f} KB\nType: {ext}",
                          bg=self.colors['bg_primary'],
                          fg=self.colors['text_secondary'],
                          font=('Segoe UI', 9))
        file_info.pack(padx=10, pady=10)
        
        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)
    
    def show_conv_context_menu(self, event):
        """Affiche le menu contextuel pour les conversations"""
        try:
            self.conversations_list.selection_clear(0, tk.END)
            index = self.conversations_list.nearest(event.y)
            self.conversations_list.selection_set(index)
            self.conv_context_menu.post(event.x_root, event.y_root)
        finally:
            self.conv_context_menu.grab_release()
    
    def delete_conversation(self):
        """Supprime la conversation sélectionnée"""
        selection = self.conversations_list.curselection()
        if selection:
            index = selection[0]
            if messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cette conversation ?"):
                self.conversations_list.delete(index)
                
                if index < len(self.conversations):
                    conv_id = self.conversations[index]["id"]
                    file_path = f"conversations/{conv_id}.json"
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    del self.conversations[index]
                
                if self.current_conversation_id == conv_id:
                    self.new_conversation()
    
    def save_conversation(self):
        """Sauvegarde la conversation actuelle"""
        if not self.current_conversation:
            return
            
        if not self.current_conversation_id:
            self.current_conversation_id = f"conv_{int(time.time())}"
            
        title = "Nouvelle discussion"
        for msg in self.current_conversation:
            if msg["role"] == "user":
                title = msg["content"][:30] + "..." if len(msg["content"]) > 30 else msg["content"]
                break
                
        data = {
            "id": self.current_conversation_id,
            "title": title,
            "messages": self.current_conversation,
            "timestamp": datetime.now().isoformat()
        }
        
        self.conv_manager.save_conversation(data)
            
        self.load_conversations()
        
        for i, conv in enumerate(self.conversations):
            if conv["id"] == self.current_conversation_id:
                self.conversations_list.selection_clear(0, tk.END)
                self.conversations_list.selection_set(i)
                break
    
    def load_conversations(self):
        """Charge les conversations sauvegardées"""
        self.conversations = []
        self.conversations_list.delete(0, tk.END)
        
        if not os.path.exists("conversations"):
            return
            
        conversation_files = []
        for file_name in os.listdir("conversations"):
            if file_name.endswith(".json"):
                conversation_files.append(file_name)
        
        conversation_files.sort(key=lambda x: os.path.getmtime(os.path.join("conversations", x)), reverse=True)
        
        for file_name in conversation_files:
            try:
                file_path = os.path.join("conversations", file_name)
                data = self.conv_manager.load_conversation_file(file_path)
                
                self.conversations.append(data)
                self.conversations_list.insert(tk.END, data["title"])
            except Exception as e:
                print(f"Erreur lors du chargement de {file_name}: {e}")
        
    def load_model_dialog(self):
        """Dialogue de chargement de modèle"""
        if self.is_loading:
            return
            
        file_path = filedialog.askopenfilename(
            title="Sélectionner un modèle GGUF",
            filetypes=[("GGUF files", "*.gguf"), ("ZIP files", "*.zip"), ("All files", "*.*")]
        )
        
        if file_path:
            self.model_btn.config(state='disabled', text="⏳ Chargement...")
            self.status_label.config(text="● Préparation...", fg=self.colors['warning'])
            self.progress_bar.pack(side='left', fill='x', expand=True)
            self.progress_label.pack(side='right', padx=(5, 0))
            self.progress_bar['value'] = 0
            self.progress_label.config(text="0%")
            
            threading.Thread(target=self.load_model_thread, args=(file_path,), daemon=True).start()
            
    def send_message(self):
        """Envoi du message avec streaming"""
        if self.is_loading or not self.model or self.is_generating:
            return
            
        message = self.input_text.get("1.0", tk.END).strip()
        if not message and not self.attached_files:
            return
        
        if len(self.current_conversation) == 0:
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
        
        if not self.current_conversation:
            self.current_conversation_id = f"conv_{int(time.time())}"
            self.conv_title.config(text="Nouvelle discussion")
        
        # Préparer le message complet
        full_message = message
        
        # Ajouter des informations sur les fichiers attachés
        for file_path in self.attached_files:
            filename = os.path.basename(file_path)
            ext = os.path.splitext(file_path)[1].lower()
            
            full_message += f"\n\n[Fichier joint: {filename}]"
            
            if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                full_message += "\nℹ️ Ceci est une image. Llama.cpp ne peut pas analyser son contenu."
            elif ext == '.txt':
                # Ajouter le contenu texte
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        text_content = f.read()
                        full_message += f"\n\nContenu du fichier texte:\n{text_content}"
                except:
                    full_message += "\n❌ Impossible de lire le fichier texte."
        
        # Ajouter le message utilisateur
        self.current_conversation.append({
            "role": "user", 
            "content": full_message, 
            "timestamp": datetime.now().isoformat()
        })
        
        if message:
            self.display_user_message(message)
        elif self.attached_files:
            self.display_user_message(f"[{len(self.attached_files)} fichier(s) joint(s)]")
        
        self.save_conversation()
        
        # Effacer les champs
        self.input_text.delete("1.0", tk.END)
        self.attach_label.config(text="")
        self.attached_files = []
        if hasattr(self, 'last_extracted_text'):
            delattr(self, 'last_extracted_text')
        
        self.send_btn.config(state='disabled', bg=self.colors['accent'])
        self.status_label.config(text="● Génération...", fg=self.colors['warning'])
        self.stop_btn.config(state='normal')
        self.typing_label.config(text="")
        
        # Créer un message vide pour le streaming
        self.create_streaming_message()
        
        # Génération avec streaming
        threading.Thread(target=self.generate_response_streaming, args=(full_message,), daemon=True).start()
        
    def create_streaming_message(self):
        """Crée un message vide pour le streaming"""
        message_frame = tk.Frame(self.scrollable_frame, bg=self.colors['bg_primary'])
        message_frame.pack(fill='x', padx=20, pady=8)
        self.current_streaming_frame = message_frame

        avatar_frame = tk.Frame(message_frame, bg=self.colors['bg_primary'])
        avatar_frame.pack(anchor='w', side='left')

        avatar = tk.Label(avatar_frame, text="🤖",
                          bg=self.colors['bg_primary'], fg=self.colors['accent'],
                          font=('Segoe UI', 12))
        avatar.pack(padx=(0, 12))

        self.current_ai_message_label = tk.Label(
            message_frame,
            text="▌",
            bg=self.colors['bg_primary'],
            fg=self.colors['text_primary'],
            font=('Segoe UI', 11),
            wraplength=900,
            justify='left',
            anchor='w',          
            relief='flat', bd=0
        )
        self.current_ai_message_label.pack(anchor='w', fill='x', padx=(50, 20))

        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)
        
    def update_streaming_message(self, text):
        """Met à jour le message pendant le streaming"""
        if self.current_ai_message_label and self.current_ai_message_label.winfo_exists():
            display_text = text + " ▌"
            self.current_ai_message_label.config(text=display_text, justify='left', anchor='w')
            
            self.chat_canvas.update_idletasks()
            self.chat_canvas.yview_moveto(1.0)
        
    def finalize_streaming_message(self, final_text):
        """Finalise le message après streaming"""
        if self.current_streaming_frame and self.current_streaming_frame.winfo_exists():
            self.current_streaming_frame.destroy()
            self.current_streaming_frame = None
        
        self.display_ai_message_with_code(final_text)
        
        self.status_label.config(text="● Prêt", fg=self.colors['success'])
        self.send_btn.config(state='normal', bg=self.colors['accent_hover'])
        self.stop_btn.config(state='disabled')
    
    def display_ai_message_with_code(self, message):
        """Affiche un message IA avec gestion des blocs de code"""
        message_frame = tk.Frame(self.scrollable_frame, bg=self.colors['bg_primary'])
        message_frame.pack(fill='x', padx=20, pady=8)

        avatar_frame = tk.Frame(message_frame, bg=self.colors['bg_primary'])
        avatar_frame.pack(anchor='w', side='left')

        avatar = tk.Label(avatar_frame, text="🤖",
                          bg=self.colors['bg_primary'], fg=self.colors['accent'],
                          font=('Segoe UI', 12))
        avatar.pack(padx=(0, 12))

        content_frame = tk.Frame(message_frame, bg=self.colors['bg_primary'])
        content_frame.pack(anchor='w', fill='x', expand=True, padx=(50, 20))

        # Détecter les blocs de code
        code_blocks = self.extract_code_blocks(message)
    
        if code_blocks:
            current_pos = 0
            for i, (code, lang, start, end) in enumerate(code_blocks):
                if start > current_pos:
                    text_before = message[current_pos:start]
                    if text_before.strip():
                        text_label = tk.Label(
                            content_frame,
                            text=text_before,
                            bg=self.colors['bg_primary'],
                            fg=self.colors['text_primary'],
                            font=('Segoe UI', 11),
                            wraplength=900,
                            justify='left',
                            anchor='w'
                        )
                        text_label.pack(anchor='w', fill='x', pady=(0, 10))
            
                # Créer le widget de code
                code_widget = CodeTextWidget(content_frame, language=lang)
                code_widget.set_code(code)
                code_widget.pack(fill='x', pady=(0, 10))
            
                # Ajouter un bouton "Voir le code complet" pour les codes longs
                if len(code.split('\n')) > 20:
                    full_code_btn = tk.Button(
                        content_frame,
                        text="📄 Voir le code complet",
                        command=lambda c=code, l=lang: self.show_full_code_window(c, l),
                        bg=self.colors['bg_primary'],
                        fg=self.colors['accent'],
                        font=('Segoe UI', 9),
                        relief='flat',
                        cursor='hand2'
                    )
                    full_code_btn.pack(anchor='w', pady=(0, 10))
            
                current_pos = end
    
            if current_pos < len(message):
                text_after = message[current_pos:]
                if text_after.strip():
                    text_label = tk.Label(
                        content_frame,
                        text=text_after,
                        bg=self.colors['bg_primary'],
                        fg=self.colors['text_primary'],
                        font=('Segoe UI', 11),
                        wraplength=900,
                        justify='left',
                        anchor='w'
                    )
                    text_label.pack(anchor='w', fill='x')
        else:
            text_label = tk.Label(
                content_frame,
                text=message,
                bg=self.colors['bg_primary'],
                fg=self.colors['text_primary'],
                font=('Segoe UI', 11),
                wraplength=900,
                justify='left',
                anchor='w'
            )
            text_label.pack(anchor='w', fill='x')

        button_frame = tk.Frame(message_frame, bg=self.colors['bg_primary'])
        button_frame.pack(fill='x', padx=70, pady=(0, 8))

        copy_btn = tk.Button(
            button_frame, text="📋 Copier",
            command=lambda: self.copy_text(message),
            bg=self.colors['bg_primary'], fg=self.colors['text_secondary'],
            font=('Segoe UI', 8),
            relief='flat', bd=0,
            cursor='hand2'
        )
        copy_btn.pack(side='right')

        self.current_ai_message_label = None
        self.streaming_text = ""
        
    def extract_code_blocks(self, text):
        """Extrait les blocs de code du texte"""
        # Pattern amélioré pour capturer les blocs de code même mal formés
        pattern = r'```(\w+)?\s*\n(.*?)```'
        matches = list(re.finditer(pattern, text, re.DOTALL))
        
        code_blocks = []
        for match in matches:
            lang = match.group(1) or "text"
            code = match.group(2).strip()
            start, end = match.span()
            code_blocks.append((code, lang, start, end))
        
        # Si pas de bloc détecté mais que ça ressemble à du code Python
        if not code_blocks and self.looks_like_python_code(text):
            code_blocks.append((text.strip(), "python", 0, len(text)))
        
        return code_blocks
        
    def display_user_message(self, message):
        """Affichage du message utilisateur"""
        message_frame = tk.Frame(self.scrollable_frame, bg=self.colors['bg_primary'])
        message_frame.pack(fill='x', padx=20, pady=8)

        content_frame = tk.Frame(message_frame, bg=self.colors['bg_primary'])
        content_frame.pack(anchor='w', fill='x', side='left', expand=True)

        avatar_frame = tk.Frame(content_frame, bg=self.colors['bg_primary'])
        avatar_frame.pack(anchor='w', side='left')

        avatar = tk.Label(avatar_frame, text="👤",
                          bg=self.colors['bg_primary'], fg=self.colors.get('user_text', '#000000'),
                          font=('Segoe UI', 12))
        avatar.pack(padx=(0, 12))

        msg_label = tk.Label(
            content_frame,
            text=message,
            bg=self.colors['bg_primary'],
            fg=self.colors.get('user_text', '#000000'),
            font=('Segoe UI', 11),
            wraplength=700,
            justify='left',
            anchor='w',
            relief='flat', bd=0
        )
        msg_label.pack(anchor='w', side='left', fill='x', expand=True)

        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)
        
    def display_error_message(self, message):
        """Affichage des erreurs"""
        message_frame = tk.Frame(self.scrollable_frame, bg=self.colors['bg_primary'])
        message_frame.pack(fill='x', padx=20, pady=8)
        
        error_label = tk.Label(message_frame, text=message,
                           bg=self.colors['error'], fg='white',
                           font=('Segoe UI', 10),
                           wraplength=600, justify='left',
                           padx=12, pady=8,
                           relief='flat', bd=0)
        error_label.pack(fill='x')
        
        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)
    
    def new_conversation(self):
        """Nouvelle conversation"""
        self.current_conversation = []
        self.current_conversation_id = None
        self.conv_title.config(text="Nouvelle discussion")
        
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.show_welcome_message()
    
    def load_conversation(self, event):
        """Chargement d'une conversation"""
        selection = self.conversations_list.curselection()
        if selection:
            index = selection[0]
            if index < len(self.conversations):
                conversation = self.conversations[index]
                
                self.current_conversation = conversation["messages"]
                self.current_conversation_id = conversation["id"]
                self.conv_title.config(text=conversation["title"])
                
                for widget in self.scrollable_frame.winfo_children():
                    widget.destroy()
                
                for msg in conversation["messages"]:
                    if msg["role"] == "user":
                        self.display_user_message(msg["content"])
                    else:
                        self.display_ai_message_with_code(msg["content"])
    
    def copy_conversation(self):
        """Copie de la conversation"""
        if not self.current_conversation:
            messagebox.showwarning("Attention", "Aucune conversation à copier!")
            return
            
        full_text = ""
        for msg in self.current_conversation:
            role = "Vous" if msg["role"] == "user" else "IA"
            full_text += f"{role}: {msg['content']}\n\n"
        
        self.root.clipboard_clear()
        self.root.clipboard_append(full_text.strip())
        self.status_label.config(text="● Conversation copiée", fg=self.colors['success'])
    
    def copy_text(self, text):
        """Copie d'un texte"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.config(text="● Texte copié", fg=self.colors['success'])
    
    def clear_conversation(self):
        """Effacement de la conversation"""
        if not self.current_conversation:
            return
            
        if messagebox.askyesno("Confirmation", "Voulez-vous vraiment effacer cette discussion?"):
            self.current_conversation = []
            self.current_conversation_id = None
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            self.conv_title.config(text="Nouvelle discussion")
            self.status_label.config(text="● Conversation effacée", fg=self.colors['warning'])
            self.show_welcome_message()
    
    def run(self):
        """Lancement de l'application"""
        self.root.mainloop()

def main():
    """Fonction principale"""
    if Llama is None:
        messagebox.showerror("Erreur", 
            "llama-cpp-python n'est pas installé!\n\n"
            "Installez-le avec:\n"
            "pip install llama-cpp-python")
        return
    
    app = PrometheusAI()
    app.run()

if __name__ == "__main__":
    main()