"""供应商压缩响应的有界解码；同时限制传输量和解压后总量。"""

import zlib

import brotli


class ProviderDecodeService:
    def __init__(self, encoding: str, limit: int):
        self.encoding, self.limit = encoding.lower().strip(), limit
        self.received = self.decoded = 0
        if self.encoding == 'br':
            self.decoder = brotli.Decompressor()
        elif self.encoding == 'gzip':
            self.decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif self.encoding == 'identity':
            self.decoder = None
        else:
            raise ValueError('不支持的响应压缩格式')

    def feed(self, chunk: bytes) -> bytes:
        self.received += len(chunk)
        if self.received > self.limit:
            raise ValueError('压缩响应超过容量上限')
        remaining = self.limit - self.decoded
        try:
            if self.encoding == 'br':
                result = self.decoder.process(chunk, output_buffer_limit=remaining + 1)
                if not self.decoder.can_accept_more_data():
                    raise ValueError('解压响应超过容量上限')
            elif self.encoding == 'gzip':
                result = self.decoder.decompress(chunk, remaining + 1)
                if self.decoder.unconsumed_tail or self.decoder.unused_data:
                    raise ValueError('解压响应超限或包含多余数据')
            else:
                result = chunk
        except (brotli.error, zlib.error) as error:
            raise ValueError('压缩响应损坏') from error
        self.decoded += len(result)
        if self.decoded > self.limit:
            raise ValueError('解压响应超过容量上限')
        return result

    def finish(self):
        if self.encoding == 'br' and not self.decoder.is_finished():
            raise ValueError('压缩响应不完整')
        if self.encoding == 'gzip' and not self.decoder.eof:
            raise ValueError('压缩响应不完整')
