import os
from PyQt5.QtWidgets import QWidget, QApplication, QCheckBox, QLabel, QComboBox, QSizePolicy
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt, QObject, pyqtSignal
from idaapi import *
import copy

__author__ = "Dennis Elser"

class ColorFilter():
    name = None

    def on_activate(self, idx):
        pass

    def on_mb_click(self, addr, button):
        pass
    
    def do_filter(self, buf, addr):
        return []

    def get_tooltip(self, addr):
        return None

# -----------------------------------------------------------------------

class ScreenEAHook(View_Hooks):
    def __init__(self):
        View_Hooks.__init__(self)
        self.sh = SignalHandler()
        self.new_ea = self.sh.ida_newea
    
    def view_loc_changed(self, widget, curloc, prevloc):
        if curloc is not prevloc:
            self.new_ea.emit()

# -----------------------------------------------------------------------

class SignalHandler(QObject):    
    pw_statechanged = pyqtSignal()
    ida_newea = pyqtSignal()

# -----------------------------------------------------------------------

class IDBBufHandler():
    # TODO
    def __init__(self, loaderSegmentsOnly=False):
        pass

    def get_buf(self, ea, count=0):
        # TODO: use/hook invalidate_dbgmem_contents() ?
        # TODO: implement some kind of caching mechanism?
        buf = get_bytes(ea, count)
        return buf

    def get_base(self, ea):
        base = BADADDR
        qty = get_segm_qty()
        for i in xrange(qty):
            seg = getnseg(i)
            if seg and seg.contains(ea):
                base = seg.startEA
                break
        return base
        
# -----------------------------------------------------------------------

    
class PixelWidget(QWidget):
    def __init__(self, form, bufhandler):
        super(PixelWidget, self).__init__()

        self.form = form
        self.pixelSize = 5
        self.maxPixelsPerLine = 32
        self.maxPixelsTotal = 0
        self.y = 0
        self.key = None
        self.buf = None
        self.offs = 0
        self.base = 0
        self.fm = None
        self.mouseOffs = 0
        self.numbytes = 0
        self.sync = True
        self.showcursor = True
        self.bh = bufhandler
        
        self.setMouseTracking(True)        
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.sh = SignalHandler()
        self.statechanged = self.sh.pw_statechanged
        
        self.show()

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        self._plot_buffer(qp)
        qp.end()

    def _plot_buffer(self, qp):
        size = self.size()
        self.maxPixelsTotal = self.maxPixelsPerLine * (size.height() / self.pixelSize)
        self.buf = self.bh.get_buf(self.base + self.offs, self.maxPixelsTotal)
        
        colors = []

        y = -1
        
        pen = QPen()
        pen.setWidth(self.pixelSize)

        self.numbytes = min(self.maxPixelsTotal, len(self.buf))
        addr = self.base + self.offs
        colors = self.fm.do_filter(self.buf[:self.numbytes], addr)

        for i in xrange(self.numbytes):
            x = i % (self.maxPixelsPerLine)
            _x = x * self.pixelSize
            if not x:
                y = y + 1
                _y = y * self.pixelSize

            col = colors[i]
            if self.mouseOffs == i and self.get_cursor_state():
                col.setRgb(~col.rgb())

            pen.setColor(col)
            qp.setPen(pen)
            qp.drawPoint(_x + self.pixelSize / 2, _y + self.pixelSize / 2)

    def keyPressEvent(self, event):
        self.key = event.key()
        if self.key == Qt.Key_G:
            addr = AskAddr(self.base + self.offs, "Jump to address")
            if addr is not None:
                jumpto(addr)
        elif self.key == Qt.Key_F12:
            print "TODO: implement pic export"

    def keyReleaseEvent(self, event):
        self.key = None
        
    def mousePressEvent(self, event):
        self.y = event.pos().y()
        self.fm.on_mb_click(self.get_cursor_address(), event.button())

    def mouseReleaseEvent(self, event):
        if self.get_sync_state():
            jumpto(self.base + self.offs)
            self.activateWindow()
            self.setFocus()
            self.statechanged.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            addr = self.base + self.offs + self._get_offs_by_pos(event.pos())
            jumpto(addr)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()/120

        # zoom
        if self.key == Qt.Key_Control:
            self.set_zoom_delta(delta)

        # width            
        elif self.key == Qt.Key_X:
            self.set_width_delta(delta)

        # offset (fine)
        elif self.key == Qt.Key_Shift:
            self.set_offset_delta(delta)

            if self.get_sync_state():
                jumpto(self.base + self.offs)
                self.activateWindow()
                self.setFocus()

        # offset (coarse)
        else:
            self.set_offset_delta(delta * self.maxPixelsPerLine)
            
            if self.get_sync_state():
                jumpto(self.base + self.offs)
                self.activateWindow()
                self.setFocus()

        self.statechanged.emit()
        self.repaint()
        
    def mouseMoveEvent(self, event):
        y = event.pos().y()
        
        if event.buttons() == Qt.NoButton:
            self.mouseOffs = self._get_offs_by_pos(event.pos())
            self.setToolTip(self.fm.get_tooltip(self.get_cursor_address()))

        # zoom
        elif self.key == Qt.Key_Control:
            self.set_zoom_delta(-1 if y > self.y else 1)

        # width
        elif self.key == Qt.Key_X:
            self.set_width_delta(-1 if y > self.y else 1)

        # scrolling (offset)
        elif y != self.y:
            # offset (fine)
            delta = y - self.y

            # offset (coarse)
            if self.key != Qt.Key_Shift:
                delta *= self.get_width()
                
            self.set_offset_delta(delta)

        self.y = y            
        self.statechanged.emit()
        self.repaint()

    def set_sync_state(self, sync):
        self.sync = sync

    def get_sync_state(self):
        return self.sync
    
    def set_cursor_state(self, sync):
        self.showcursor = sync

    def get_cursor_state(self):
        return self.showcursor

    def set_filter(self, filter, idx):
        self.fm = filter
        self.fm.on_activate(idx)
        self.repaint()

    def set_addr(self, ea):
        base = self.bh.get_base(ea)
        self._set_base(base)
        self._set_offs(ea - base)
        self.repaint()

    def get_zoom(self):
        return self.pixelSize

    def get_width(self):
        return self.maxPixelsPerLine

    def get_count(self):
        return self.numbytes
        
    def get_address(self):
        return self.base + self.offs

    def get_cursor_address(self):
        return self.get_address() + self.mouseOffs

    def set_zoom_delta(self, dzoom):
        self.pixelSize = max(1, self.pixelSize + dzoom)

    def set_width_delta(self, dwidth):
        self.maxPixelsPerLine = max(1, self.maxPixelsPerLine + dwidth)

    def set_offset_delta(self, doffs):
        self._set_offs(max(0, self.offs - doffs))

    def _get_offs_by_pos(self, pos):
        elemX = min(pos.x() / self.pixelSize, self.maxPixelsPerLine-1)
        elemY = min(pos.y() / self.pixelSize, self.maxPixelsTotal / self.maxPixelsPerLine - 1)
        offs = elemY * self.maxPixelsPerLine + elemX
        return offs

    def _set_offs(self, offs):
        self.offs = offs

    def _set_base(self, ea):
        self.base = ea


# -----------------------------------------------------------------------


class IDACyberForm(PluginForm):
    idbh = None
    hook = None
    windows = []

    def __init__(self):
        if IDACyberForm.idbh is None:
            IDACyberForm.idbh = IDBBufHandler(True)

        if IDACyberForm.hook is None:
            IDACyberForm.hook = ScreenEAHook()
            IDACyberForm.hook.hook()

        self.__clink__ = ida_kernwin.plgform_new()
        self.title = None
        self.filterlist = self._load_filters()
        self.pw = None
        self.windowidx = 0
                
    def _update_status_text(self):
        self.status.setText("Adress %X | Cursor %X | Zoom %d | Width %d | Bytes %d" % (
            self.pw.get_address(),
            self.pw.get_cursor_address(),
            self.pw.get_zoom(),
            self.pw.get_width(),
            self.pw.get_count()))

    def _load_filters(self):
        filterdir = idadir("plugins/cyber")
        sys.path.append(filterdir)
        filters = []
        for entry in os.listdir(filterdir):
            if ".py" in entry.lower():
                mod = os.path.splitext(entry)[0]
                filter = __import__(mod, globals(), locals(), [], 0)
                filters.append(filter.FILTER_ENTRY())
        return filters

    def _change_screen_ea(self):
        if self.pw.get_sync_state():
            ea = ScreenEA()
            self.pw.set_addr(ea)
            self._update_status_text()

    def _select_filter(self, idx):
        self.pw.set_filter(self.filterlist[idx], idx)
        self.pw.repaint()

    def _toggle_sync(self, state):
        self.pw.set_sync_state(state == Qt.Checked)

    def _toggle_cursor(self, state):
        self.pw.set_cursor_state(state == Qt.Checked)

    def Show(self, caption, options):
	i = 0
        while True:
            i += 1
            if i not in IDACyberForm.windows:
                title = "IDA Cyber - %d" % i
                caption = title
                IDACyberForm.windows.append(i)
                self.windowidx = i
                break        
        return ida_kernwin.plgform_show(self.__clink__, self, caption, options)
    
    def OnCreate(self, form):
        self.form = form
        self.parent = self.FormToPyQtWidget(form)

        vl = QtWidgets.QVBoxLayout()
        hl = QtWidgets.QHBoxLayout()
        hl2 = QtWidgets.QHBoxLayout()
        hl3 = QtWidgets.QHBoxLayout()
        hl4 = QtWidgets.QHBoxLayout()
        
        self.pw = PixelWidget(self.parent, IDACyberForm.idbh)
        self.pw.setFocusPolicy(Qt.StrongFocus | Qt.WheelFocus)
        self.pw.statechanged.connect(self._update_status_text)
        self.pw.set_filter(self.filterlist[0], 0)
        self.pw.set_addr(ScreenEA())

        vl.addWidget(self.pw)

        flt = QLabel()  
        flt.setText("Filter:")
        hl.addWidget(flt)

        self.filterChoser = QComboBox()
        self.filterChoser.addItems([filter.name for filter in self.filterlist])
        self.filterChoser.currentIndexChanged.connect(self._select_filter)
        hl.addWidget(self.filterChoser)
        hl.addStretch(1)

        self.cb = QCheckBox("Sync")
        self.cb.setChecked(True)
        self.cb.stateChanged.connect(self._toggle_sync)
        hl2.addWidget(self.cb)

        self.cb2 = QCheckBox("Highlight Cursor")
        self.cb2.setChecked(True)
        self.cb2.stateChanged.connect(self._toggle_cursor)
        hl3.addWidget(self.cb2)

        self.status = QLabel()
        self.status.setText("Cyber, cyber!")
        hl4.addWidget(self.status)

        vl.addLayout(hl)
        vl.addLayout(hl2)
        vl.addLayout(hl3)
        vl.addLayout(hl4)

        self.parent.setLayout(vl)
        if IDACyberForm.hook is not None:
                IDACyberForm.hook.new_ea.connect(self._change_screen_ea)

    def OnClose(self, options):
        options = PluginForm.FORM_SAVE | PluginForm.FORM_NO_CONTEXT
        IDACyberForm.windows.remove(self.windowidx)
        if not len(IDACyberForm.windows):
            IDACyberForm.hook.unhook()
            IDACyberForm.hook = None

# -----------------------------------------------------------------------

class IDACyberPlugin(plugin_t):
    flags = 0
    comment = ""
    help = ""
    wanted_name = "IDA Cyber"
    wanted_hotkey = "Ctrl-P"

    def init(self):
        return PLUGIN_KEEP

    def run(self, arg):
        form = IDACyberForm()
        form.Show(None, options = PluginForm.FORM_MENU|PluginForm.FORM_RESTORE|PluginForm.FORM_PERSIST)

    def term(self):
        pass

# -----------------------------------------------------------------------

def PLUGIN_ENTRY():
    return IDACyberPlugin()
