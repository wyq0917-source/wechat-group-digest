import hashlib
import ctypes
import ctypes.util
import re
import xml.etree.ElementTree as ET

def decode(value):
    if value is None: return '',[]
    if isinstance(value,str): return value,[]
    raw=bytes(value)
    if raw.startswith(b'\x28\xb5\x2f\xfd'):
        libpath=ctypes.util.find_library('zstd') or '/opt/homebrew/lib/libzstd.dylib'
        try:
            z=ctypes.CDLL(libpath)
            z.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
            z.ZSTD_decompress.restype=ctypes.c_size_t
            z.ZSTD_isError.argtypes=[ctypes.c_size_t]; z.ZSTD_isError.restype=ctypes.c_uint
            out=ctypes.create_string_buffer(16*1024*1024)
            count=z.ZSTD_decompress(out,len(out),raw,len(raw))
            if z.ZSTD_isError(count): raise ValueError('zstd')
            raw=out.raw[:count]
        except (OSError,ValueError): return '',['Zstandard 内容未能解码，仅保留来源摘要和字节数']
    try: return raw.decode('utf-8').rstrip('\0'),[]
    except UnicodeDecodeError: return '',['非 UTF-8 内容未解码，仅保留来源摘要和字节数']

def parse_content(content, local_type, known_sender=None, _depth=0):
    text,warnings=decode(content)
    kind=int(local_type)&0xffffffff
    out={'type_code':int(local_type),'type':{1:'text',3:'image',34:'voice',43:'video',47:'emoji',49:'card',10000:'system',10002:'system'}.get(kind,'unknown'),
         'text':text,'warnings':warnings,'links':[],'quote':None,'card':None}
    # Group transport prefix is only stripped when structurally recognized.
    prefix=re.match(r'^([^\s<>:]+):\n',text)
    if prefix and known_sender is None:
        candidate=text[prefix.end():]
        if candidate.lstrip().startswith('<') and '<!DOCTYPE' not in candidate.upper() and '<!ENTITY' not in candidate.upper():
            try:
                embedded=ET.fromstring(candidate)
                if embedded.findtext('.//fromusername')==prefix.group(1):
                    known_sender=prefix.group(1)
            except ET.ParseError:
                pass
    if prefix and prefix.group(1)==known_sender:
        out['sender_prefix']=prefix.group(1); text=text[prefix.end():]; out['text']=text
    xml=None
    if text.lstrip().startswith('<') and '<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper():
        try: xml=ET.fromstring(text)
        except ET.ParseError: out['warnings'].append('XML 未能解析；保留原文')
    if kind in (3,34,43,47):
        name={3:'图片',34:'语音',43:'视频',47:'表情'}[kind]
        out['text']=f'[{name}：未解析内容]'
        if kind==34 and xml is not None:
            trans=xml.find('.//voicetrans')
            if trans is not None and trans.get('transtext'):
                out['text']=trans.get('transtext'); out['transcript_source']='本地消息 XML voicetrans.transtext，未另行识别音频'
    elif kind==49 and xml is not None:
        app=xml if xml.tag=='appmsg' else xml.find('.//appmsg')
        if app is not None:
            get=lambda tag: app.findtext(tag) or ''
            out['card']={k:get(v) for k,v in {'title':'title','description':'des','url':'url','subtype':'type','filename':'title','file_extension':'appattach/fileext','file_size':'appattach/totallen'}.items()}
            out['text']=get('title') or '[卡片：无可读标题]'
            if get('des'): out['text']+='\n'+get('des')
            quote=app.find('refermsg')
            if quote is not None:
                qt=quote.findtext('type') or '0';qtext=quote.findtext('content') or ''
                if _depth<3 and qt.isdigit():qtext=parse_content(qtext,int(qt),known_sender=quote.findtext('chatusr') or None,_depth=_depth+1)['text']
                elif qtext.lstrip().startswith('<'):qtext='[嵌套引用：未进一步解析]'
                out['quote']={'server_id':quote.findtext('svrid') or '', 'sender':quote.findtext('displayname') or '', 'text':qtext, 'type':qt, 'source':'本条消息内嵌引用；不作为窗口内独立消息计数'}
            if get('url').startswith(('https://','http://')): out['links'].append(get('url'))
            finder=app.find('finderFeed')
            if finder is not None:
                desc=finder.findtext('desc') or ''
                out['card']['finder']={'description':desc,'author':finder.findtext('nickname') or '', 'object_id':finder.findtext('objectId') or '', 'source':'本地视频号卡片元数据；未解析视频内容'}
                if desc:out['text']=desc
                out['card']['url']='';out['links']=[]
        else:
            out['text']='[卡片：结构未解析]';out['warnings'].append('未知 XML 卡片结构')
    elif kind in (10000,10002) and xml is not None:
        out['text']=xml.findtext('.//revokemsg/content') or '[系统消息：结构未解析]'
    out['links']=list(dict.fromkeys(out['links']+re.findall(r'https?://[^\s<>"\x00]+',out['text'])))
    raw=bytes(content) if isinstance(content,(bytes,bytearray)) else str(content or '').encode()
    out['source_content_sha256']=hashlib.sha256(raw).hexdigest()
    out['source_content_bytes']=len(raw)
    # Do not persist transport XML/media access keys in shareable exports.
    # Parsed text, types, IDs, metadata and source digests remain auditable.
    return out
