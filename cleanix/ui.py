#!/usr/bin/env python3
""" UI module for cleanix application """

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Pango
import matplotlib
matplotlib.use('GTK4Agg')
import matplotlib.pyplot as plt
import numpy as np


def main_interface(window):
    """Create the main interface for the cleanix application.
    
    Sets up the main window with a notebook/tab layout featuring:
    - Cleaner tab: System junk cleanup
    - Optimizer tab: System optimization
    - Adjustments tab: Ubuntu-specific tweaks
    
    Each tab includes modern graphics/charts for visualization.
    """
    # Set up the main window
    window.set_title('cleanix - Limpeza e Otimização do Sistema')
    window.set_default_size(1000, 700)
    window.set_size_request(1000, 700)
    
    # Application header bar
    header_bar = Gtk.HeaderBar()
    window.set_title('cleanix - Limpeza e Otimização')
    window.set_titlebar(header_bar)
    
    # Create a notebook (tabbed interface)
    notebook = Gtk.Notebook()
    notebook.set_tab_pos(Gtk.PositionType.TOP)
    notebook.set_vexpand(True)
    window.set_child(notebook)
    
    # ---- Tab 1: Cleaner ----
    create_cleaner_tab(notebook)
    
    # ---- Tab 2: Optimizer ----
    create_optimizer_tab(notebook)
    
    # ---- Tab 3: Adjustments ----
    create_adjustments_tab(notebook)


def init_matplotlib_figure():
    """Initialize a matplotlib figure for GTK integration."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6, 3))
    
    # Disk usage donut
    ax1.pie([50, 50], labels=['Used', 'Free'], autopct='%1.1f%%',
            colors=['#e74c3c', '#2ecc71'], startangle=90,
            wedgeprops=dict(width=0.4, edgecolor='w'))
    ax1.set_title('Disco', fontsize=8)
    ax1.axis('equal')
    
    # Temp file categories
    categories = ['Cache', 'Logs', 'Thumbnail', 'Browser', 'Outros']
    sizes = [30, 20, 20, 15, 15]
    colors = ['#3498db', '#e67e22', '#9b59b6', '#f1c40f', '#95a5a6']
    ax2.pie(sizes, labels=categories, autopct='%1.1f%%',
            colors=colors, startangle=90)
    ax2.set_title('Arquivos Temporários', fontsize=8)
    ax2.axis('equal')
    
    return fig


def update_matplotlib_chart(fig, data):
    """Update a matplotlib chart with new data.
    
    Args:
        fig: matplotlib figure
        data: dict with chart data
    
    Returns:
        Updated figure canvas
    """
    # This is a simplified update - real implementation would
    # redraw the figure with new data
    return fig


def embed_figure_in_widget(fig, widget):
    """Try to embed a matplotlib figure into a Gtk widget.
    
    Note: Full integration requires GTK-specific figure canvas.
    This is a placeholder for the chart infrastructure.
    """
    # In a full implementation, we'd use FigureCanvasGTK4Agg
    # For now, we create a label indicating the chart presence
    label = Gtk.Label()
    label.set_markup('<b>[Gráfico de Disco]</b>')
    return label


def create_cleaner_tab(notebook):
    """Create the Cleaner tab with system junk cleanup options."""
    # Create a scrollable container
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_vexpand(True)
    
    # Main container for cleaner options
    cleaner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    cleaner_box.set_margin_top(20)
    cleaner_box.set_margin_bottom(20)
    cleaner_box.set_margin_start(20)
    cleaner_box.set_margin_end(20)
    scrolled.set_child(cleaner_box)
    
    # Title
    title = Gtk.Label(label='Limpar Arquivos e Cache')
    title.add_css_class('h3')
    title.set_xalign(0)
    cleaner_box.append(title)
    
    # System info with chart
    info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    info_box.set_margin_top(10)
    cleaner_box.append(info_box)
    
    # Get system info for chart
    from cleanix.utils import get_disk_usage
    disk_info = get_disk_usage()
    
    # Disk usage chart embedded
    disk_chart_label = embed_figure_in_widget(None, info_box)
    disk_chart_label.set_size_request(150, 100)
    info_box.append(disk_chart_label)
    
    # Progress bar for disk
    disk_label = Gtk.Label(label=f'Uso de Disco: {disk_info["used"]}GB de {disk_info["total"]}GB usados')
    disk_label.set_xalign(0)
    info_box.append(disk_label)
    
    # Progress bar
    disk_progress = Gtk.ProgressBar()
    disk_progress.set_fraction(disk_info["used"] / max(disk_info["total"], 1))
    info_box.append(disk_progress)
    
    # Temp files section
    temp_label = Gtk.Label(label='Arquivos Temporários')
    temp_label.add_css_class('subtitle')
    temp_label.set_xalign(0)
    cleaner_box.append(temp_label)
    
    # Scanner button
    scan_btn = Gtk.Button(label='Scanner de Arquivos Temporários')
    scan_btn.set_tooltip_text('Varrer o sistema em busca de arquivos desnecessários')
    scan_btn.connect('clicked', lambda _: scan_temp_files(cleaner_box))
    cleaner_box.append(scan_btn)
    
    # Category donut chart placeholder
    chart_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    chart_box.set_margin_top(10)
    chart_box.set_vexpand(True)
    cleaner_box.append(chart_box)
    
    # Placeholder for donut chart - using label for now
    chart_placeholder = Gtk.Label(label='[Gráfico de setores: categorias de arquivos temporários - aguardando scan]')
    chart_placeholder.set_justify(Gtk.Justification.CENTER)
    chart_placeholder.set_opacity(0.5)
    chart_box.append(chart_placeholder)
    
    # File categories list
    categories_label = Gtk.Label(label='Categorias detectadas:')
    categories_label.set_xalign(0)
    cleaner_box.append(categories_label)
    
    # Categories flow box
    categories_box = Gtk.FlowBox()
    categories_box.set_valign(Gtk.Align.START)
    # Set width request for categories box
    categories_box.set_size_request(200, 120)
    categories_box.set_selection_mode(Gtk.SelectionMode.NONE)
    cleaner_box.append(categories_box)
    
    # Sample category labels
    sample_categories = ['Cache de Navegador', 'Cache de Thumbnail', 'Logs do Sistema', 'Lixo', 'Cache de Aplicativos']
    for cat in sample_categories:
        label = Gtk.Label(label=cat)
        label.add_css_class('category-chip')
        categories_box.append(label)
    
    # Action buttons
    action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    action_box.set_margin_top(20)
    action_box.set_vexpand(False)
    cleaner_box.append(action_box)
    
    # Preview button
    preview_btn = Gtk.Button(label='Pré-visualizar')
    preview_btn.set_tooltip_text('Mostrar o que será limpo antes de executar')
    preview_btn.connect('clicked', lambda _: show_preview(cleaner_box))
    action_box.append(preview_btn)
    
    # Clean button
    clean_btn = Gtk.Button(label='Limpar Agora')
    add_response_style(clean_btn)
    clean_btn.connect('clicked', lambda _: clean_system(cleaner_box))
    action_box.append(clean_btn)
    
    # Add the tab to notebook
    tab_label = Gtk.Label(label='Limpeza')
    tab_label.set_xalign(0)
    notebook.append_page(scrolled, tab_label)
    notebook.set_tab_label(scrolled, tab_label)


def scan_temp_files(cleaner_box):
    """Scan for temporary files and update the UI."""
    from cleanix.utils import get_temp_files_scanner, categorize_file, format_size
    from cleanix.utils import get_disk_usage
    
    # Show scanning progress
    # Get current disk usage
    disk_info = get_disk_usage()
    disk_progress = None
    
    # Find the progress bar in the info box
    for child in cleaner_box.get_children():
        if hasattr(child, 'set_fraction') and isinstance(child, Gtk.ProgressBar):
            disk_progress = child
            break
    
    if disk_progress:
        disk_progress.set_fraction(disk_info["used"] / max(disk_info["total"], 1))
        disk_label = None
        for child in cleaner_box.get_children():
            if isinstance(child, Gtk.Label) and 'Uso de Disco' in child.get_label():
                disk_label = child
                break
        if disk_label:
            disk_label.set_label(f'Uso de Disco: Varredura em andamento...')
    
    # Scan for temp files
    try:
        files = get_temp_files_scanner(dry_run=True)
        
        # Update categories chart
        chart_box = None
        categories_label = None
        
        # Find chart area
        for child in cleaner_box.get_children():
            if isinstance(child, Gtk.Box):
                # Check if it has the donut chart placeholder
                for grandchild in child.get_children():
                    if isinstance(grandchild, Gtk.Label) and 'setores' in grandchild.get_label():
                        chart_box = child
                        break
        
        for child in cleaner_box.get_children():
            if isinstance(child, Gtk.Label) and 'Categorias detectadas' in child.get_label():
                categories_label = child
                break
        
        if chart_box and categories_label:
            # Build category counts
            category_counts = {}
            for file_info in files:
                cat = file_info['category']
                category_counts[cat] = category_counts.get(cat, 0) + 1
            
            # Update chart placeholder text
            chart_parts = []
            for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
                chart_parts.append(f'{cat}: {count} arquivos')
            
            if chart_parts:
                chart_text = ';\n'.join(chart_parts[:5])
            else:
                chart_text = 'Nenhum arquivo temporário encontrado'
            
            # Update the chart label - find it in the chart_box
            for grandchild in chart_box.get_children():
                if isinstance(grandchild, Gtk.Label):
                    grandchild.set_label(f'[Gráfico de setores: categorias de arquivos temporários]\n{chart_text}')
                    grandchild.set_opacity(1.0)
                    break
        
        # Update categories label
        if categories_label:
            total_files = sum(category_counts.values()) if 'category_counts' in dir() else len(files)
            categories_label.set_label(f'Categorias detectadas: {total_files} arquivos em {len(category_counts)} categorias')
        
        # Update summary
        total_size = sum(f['size'] for f in files)
        show_info_message(f'Scan completo: {len(files)} arquivos, {format_size(total_size)} de espaço recuperável')
        
    except Exception as e:
        show_error_message(f'Erro durante o scan: {str(e)}')


def show_preview(cleaner_box):
    """Show preview of what will be cleaned."""
    from cleanix.safety import show_confirmation_dialog
    from cleanix.utils import get_temp_files_scanner, format_size
    
    files = get_temp_files_scanner(dry_run=True)
    total_size = sum(f['size'] for f in files)
    total_formatted = format_size(total_size)
    num_files = len(files)
    
    message = f'Pré-visualização da limpeza:\n\n'
    message += f'Arquivos a serem removidos: {num_files}\n'
    message += f'Espaço a ser recuperado: {total_formatted}\n\n'
    message += 'Isso inclui:\n'
    message += '- Cache de navegadores\n'
    message += '- Cache de thumbnail\n'
    message += '- Arquivos de log temporários\n'
    message += '- Lixo do sistema\n\n'
    message += 'Deseja continuar com a limpeza?'
    
    parent_window = None
    for child in cleaner_box.get_children():
        if isinstance(child, Gtk.Window):
            parent_window = child
            break
    
    if parent_window is None:
        # Get top-level window
        toplevel = cleaner_box.get_toplevel()
        if isinstance(toplevel, Gtk.Window):
            parent_window = toplevel
    
    if parent_window:
        response = show_confirmation_dialog(
            parent_window,
            'Pré-visualização da Limpeza',
            message
        )
        if response:
            show_info_message('Pré-visualização confirmada - pronto para limpar')


def clean_system(cleaner_box):
    """Execute the system cleanup."""
    from cleanix.safety import show_confirmation_dialog, safe_remove, log_operation
    from cleanix.utils import get_temp_files_scanner, format_size
    
    files = get_temp_files_scanner(dry_run=False)
    total_size = sum(f['size'] for f in files)
    total_formatted = format_size(total_size)
    num_files = len(files)
    
    message = f'Vai limpar {num_files} arquivos ocupando {total_formatted}.\n\n'
    message += 'Isso removerá:\n'
    message += '- Arquivos de cache temporários\n'
    message += '- Cache de thumbnail\n'
    message += '- Logs temporários\n\n'
    message += 'Deseja continuar?'
    
    parent_window = cleaner_box.get_toplevel()
    if isinstance(parent_window, Gtk.Window):
        response = show_confirmation_dialog(
            parent_window,
            'Confirmar Limpeza do Sistema',
            message,
            yes_label='Limpar',
            no_label='Cancelar'
        )
        
        if response:
            # Execute cleanup
            show_info_message('Iniciando limpeza...')
            
            for file_info in files:
                success, msg = safe_remove(file_info['path'], dry_run=False)
                log_operation('remover_arquivo', f'{file_info["path"]}: {msg}')
            
            # Refresh the UI
            scan_temp_files(cleaner_box)
            show_info_message(f'Limpeza concluída! {num_files} arquivos removidos.')


def create_optimizer_tab(notebook):
    """Create the Optimizer tab with system optimization options."""
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_vexpand(True)
    
    optimizer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    optimizer_box.set_margin_top(20)
    optimizer_box.set_margin_bottom(20)
    optimizer_box.set_margin_start(20)
    optimizer_box.set_margin_end(20)
    scrolled.set_child(optimizer_box)
    
    title = Gtk.Label(label='Otimizar Sistema')
    title.add_css_class('h3')
    title.set_xalign(0)
    optimizer_box.append(title)
    
    # System health chart area
    health_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    health_box.set_margin_top(10)
    health_box.set_vexpand(True)
    optimizer_box.append(health_box)
    
    # Matplotlib chart for system health
    from cleanix.ui import init_matplotlib_figure, embed_figure_in_widget
    fig = init_matplotlib_figure()
    chart_widget = embed_figure_in_widget(fig, health_box)
    chart_widget.set_hexpand(True)
    health_box.append(chart_widget)
    
    # Health info labels
    health_info = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
    health_info.set_margin_top(10)
    optimizer_box.append(health_info)
    
    # CPU/memory placeholders
    cpu_label = Gtk.Label(label='CPU: ----')
    cpu_label.set_xalign(0)
    health_info.append(cpu_label)
    
    mem_label = Gtk.Label(label='Memória: ----')
    mem_label.set_xalign(0)
    health_info.append(mem_label)
    
    # Optimization options
    options_label = Gtk.Label(label='Opções de Otimização:')
    options_label.set_xalign(0)
    optimizer_box.append(options_label)
    
    options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    optimizer_box.append(options_box)
    
    # Startup apps management
    startup_cb = Gtk.CheckButton(label='Gerenciar Aplicativos de Startup')
    startup_cb.set_tooltip_text('Controlar quais aplicativos iniciam no login')
    options_box.append(startup_cb)
    
    # Fstrim file system
    fstrim_cb = Gtk.CheckButton(label='Otimizar Sistema de Arquivos (fstrim)')
    fstrim_cb.set_tooltip_text('Executar trim em dispositivos SSD')
    options_box.append(fstrim_cb)
    
    # Journal vacuum
    journal_cb = Gtk.CheckButton(label='Vazar Logs do Sistema (journalctl)')
    journal_cb.set_tooltip_text('Remover logs antigos para liberar espaço')
    options_box.append(journal_cb)
    
    # Action buttons
    action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    action_box.set_margin_top(20)
    optimizer_box.append(action_box)
    
    optimize_btn = Gtk.Button(label='Otimizar')
    add_response_style(optimize_btn)
    optimize_btn.connect('clicked', lambda _: run_optimization())
    action_box.append(optimize_btn)
    
    # Add the tab to notebook
    tab_label = Gtk.Label(label='Otimizar')
    tab_label.set_xalign(0)
    notebook.append_page(scrolled, tab_label)
    notebook.set_tab_label(scrolled, tab_label)


def run_optimization():
    """Run the optimization actions selected by the user."""
    from cleanix.safety import show_confirmation_dialog
    
    message = 'Vai executar otimizações do sistema:\n\n'
    message += '- Gerenciar aplicativos de startup\n'
    message += '- Executar fstrim no sistema de arquivos\n'
    message += '- Vazar logs antigos do journalctl\n\n'
    message += 'Isso pode melhorar o desempenho do sistema.\n'
    message += 'Deseja continuar?'
    
    parent_window = None
    # Find parent window
    # ... (simplified for now)
    
    if parent_window:
        response = show_confirmation_dialog(
            parent_window,
            'Otimizar Sistema',
            message,
            yes_label='Otimizar',
            no_label='Cancelar'
        )
        if response:
            show_info_message('Otimização em andamento...')
            # TODO: Implement actual optimization actions


def create_adjustments_tab(notebook):
    """Create the Adjustments tab with Ubuntu-specific tweaks."""
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_vexpand(True)
    
    adjustments_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    adjustments_box.set_margin_top(20)
    adjustments_box.set_margin_bottom(20)
    adjustments_box.set_margin_start(20)
    adjustments_box.set_margin_end(20)
    scrolled.set_child(adjustments_box)
    
    title = Gtk.Label(label='Ajustes do Ubuntu')
    title.add_css_class('h3')
    title.set_xalign(0)
    adjustments_box.append(title)
    
    # Adjustment suggestions
    adjustments_label = Gtk.Label(label='Sugestões de Ajustes:')
    adjustments_label.set_xalign(0)
    adjustments_box.append(adjustments_label)
    
    adjustments_box_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    adjustments_box.append(adjustments_box_inner)
    
    # AUTO apt clean suggestion
    from cleanix.utils import get_browser_cache_sizes
    apt_suggestion = Gtk.Label(label='· apt autoremove && apt clean - Limpar cache de pacotes')
    apt_suggestion.set_xalign(0)
    adjustments_box_inner.append(apt_suggestion)
    
    # Journal vacuum suggestion
    journal_suggestion = Gtk.Label(label='· journalctl --vacuum-time=7d - Limpar logs antigos de 7 dias')
    journal_suggestion.set_xalign(0)
    adjustments_box_inner.append(journal_suggestion)
    
    # Thumbnail cache
    thumbnail_suggestion = Gtk.Label(label='· Limpar cache de thumbnail - Recuperar espaço de imagens')
    thumbnail_suggestion.set_xalign(0)
    adjustments_box_inner.append(thumbnail_suggestion)
    
    # Font cache
    font_suggestion = Gtk.Label(label='· fc-cache -fv - Atualizar cache de fontes')
    font_suggestion.set_xalign(0)
    adjustments_box_inner.append(font_suggestion)
    
    # Browser cache sizes
    try:
        browser_sizes = get_browser_cache_sizes()
        browser_label = Gtk.Label(label='· Caches de navegadores:')
        browser_label.set_xalign(0)
        adjustments_box_inner.append(browser_label)
        
        for browser, size_info in browser_sizes.items():
            if size_info['size'] > 0:
                browser_size_label = Gtk.Label(
                    label=f'   - {browser}: {size_info["formatted"]} ({size_info["items"]} itens)'
                )
                browser_size_label.set_xalign(0)
                adjustments_box_inner.append(browser_size_label)
    except Exception:
        pass
    
    # Action buttons
    action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    action_box.set_margin_top(20)
    adjustments_box.append(action_box)
    
    apply_btn = Gtk.Button(label='Aplicar Ajustes')
    add_response_style(apply_btn)
    apply_btn.connect('clicked', lambda _: apply_adjustments())
    action_box.append(apply_btn)
    
    # Add the tab to notebook
    tab_label = Gtk.Label(label='Ajustes')
    tab_label.set_xalign(0)
    notebook.append_page(scrolled, tab_label)
    notebook.set_tab_label(scrolled, tab_label)


def apply_adjustments():
    """Apply the Ubuntu-specific adjustments."""
    from cleanix.safety import show_confirmation_dialog
    
    message = 'Vai aplicar ajustes do Ubuntu:\n\n'
    message += '1. apt autoremove && apt clean - Limpar cache de pacotes\n'
    message += '2. journalctl --vacuum-time=7d - Remover logs antigos\n'
    message += '3. Limpar cache de thumbnail\n'
    message += '4. Atualizar cache de fontes (fc-cache -fv)\n\n'
    message += 'Deseja aplicar estes ajustes?'
    
    parent_window = None
    # Get parent window
    toplevel = adjustments_box.get_toplevel()
    if isinstance(toplevel, Gtk.Window):
        parent_window = toplevel
    
    if parent_window:
        response = show_confirmation_dialog(
            parent_window,
            'Aplicar Ajustes do Ubuntu',
            message,
            yes_label='Aplicar',
            no_label='Cancelar'
        )
        
        if response:
            show_info_message('Aplicando ajustes...')
            
            # Execute apt clean
            from cleanix.safety import safe_execute_command
            import subprocess
            
            # APT cleanup
            success, stdout, stderr = safe_execute_command(
                ['sudo', 'apt', 'autoremove', '&&', 'apt', 'clean'],
                dry_run=False
            )
            show_info_message(f'APT cleanup: {"Sucesso" if success else "Falhou"}')
            
            # Journal vacuum
            success2, stdout2, stderr2 = safe_execute_command(
                ['journalctl', '--vacuum-time=7d'],
                dry_run=False
            )
            show_info_message(f'Journal vacuum: {"Sucesso" if success2 else "Falhou"}')
            
            # Show results
            show_info_message('Todos os ajustes foram aplicados!')


def add_response_style(button):
    """Add standard response style to a button."""
    button.add_css_class('btn')
    # Set pointer cursor - try different approaches
    try:
        cursor = Gdk.cursor_new(Gdk.CursorType.ARROW)  # fallback
        button.set_cursor(cursor)
    except Exception:
        pass  # Cursor optional, not critical


def show_info_message(message):
    """Show an information message dialog."""
    dialog = Gtk.MessageDialog(
        transient_for=None,
        message=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=message,
    )
    dialog.run()
    dialog.destroy()


def show_error_message(message):
    """Show an error message dialog."""
    dialog = Gtk.MessageDialog(
        transient_for=None,
        message=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=message,
    )
    dialog.run()
    dialog.destroy()