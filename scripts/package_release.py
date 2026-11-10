"""Cria os dois anexos da Release sem alterar as pastas de origem."""
import argparse
import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import time
from pathlib import Path
import zipfile

BASE = Path(__file__).resolve().parents[1]
FOLDERS = ('dataset_full', 'final_experiment')
LIMIT = 2 * 1024 ** 3


def inventory(source):
    """DirEntry reutiliza os metadados da enumeracao no Windows."""
    records = {}
    pending = [source]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                if entry.name == '.git':
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                else:
                    info = entry.stat()
                    name = Path(entry.path).relative_to(BASE).as_posix()
                    records[name] = (info.st_size, info.st_mtime_ns, info.st_mode)
    return records


class StreamingOutput:
    """ZIP sequencial: evita uma busca e flush para cada arquivo pequeno."""
    def __init__(self, stream):
        self.stream = stream
        self.position = 0

    def write(self, data):
        count = self.stream.write(data)
        self.position += count
        return count

    def tell(self):
        return self.position

    def seek(self, *args):
        raise OSError('Sequential ZIP output')

    def flush(self):
        self.stream.flush()


def write_zip(destination, snapshot):
    # Leitura concorrente com fila limitada; gravacao e compressao em ordem.
    names = iter(sorted(snapshot))
    with destination.open('xb', buffering=8 * 1024 * 1024) as stream, ThreadPoolExecutor(max_workers=16) as readers:
        queue = deque()
        def enqueue():
            name = next(names, None)
            if name is not None:
                queue.append((name, readers.submit((BASE / name).read_bytes)))
        for _ in range(24):
            enqueue()
        with zipfile.ZipFile(StreamingOutput(stream), 'w', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as archive:
            last_update = time.monotonic()
            count = 0
            while queue:
                name, future = queue.popleft()
                data = future.result()
                size, modified, mode = snapshot[name]
                if len(data) != size:
                    raise RuntimeError(f'Arquivo mudou durante a leitura: {name}')
                info = zipfile.ZipInfo(name, time.localtime(modified / 1e9)[:6])
                info.external_attr = mode << 16
                archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
                count += 1
                enqueue()
                if time.monotonic() - last_update >= 20:
                    print(f'{destination.name}: {count:,}/{len(snapshot):,} arquivos', flush=True)
                    last_update = time.monotonic()


def package(folder, output):
    source = BASE / folder
    if not source.is_dir():
        raise FileNotFoundError(source)
    destination = output / (folder + '.zip')
    if destination.exists():
        raise FileExistsError(destination)
    print(f'{folder}: inventariando...', flush=True)
    snapshot = inventory(source)
    print(f'{folder}: compactando {len(snapshot):,} arquivos...', flush=True)
    write_zip(destination, snapshot)
    print(f'{folder}: verificando inventario e CRC...', flush=True)
    with zipfile.ZipFile(destination) as archive:
        contents = {i.filename: i.file_size for i in archive.infolist() if not i.is_dir()}
        if contents != {name: value[0] for name, value in snapshot.items()}:
            raise RuntimeError('Inventario do ZIP diverge da origem')
        if any('.git' in Path(name).parts for name in archive.namelist()):
            raise RuntimeError('Metadados Git encontrados no ZIP')
        failure = archive.testzip()
        if failure:
            raise RuntimeError(f'Falha no CRC do ZIP: {failure}')
    if inventory(source) != snapshot:
        raise RuntimeError(f'Arquivos de origem mudaram durante o empacotamento: {source}')
    size = destination.stat().st_size
    if size >= LIMIT:
        raise RuntimeError(f'Anexo excede o limite de 2 GiB: {destination}')
    print(f'OK: {destination} | {size / 1024 ** 2:.1f} MiB | {len(snapshot):,} arquivos', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    for folder in FOLDERS:
        if output.is_relative_to((BASE / folder).resolve()):
            parser.error('A pasta de saida nao pode ficar dentro dos dados de origem')
        if (output / (folder + '.zip')).exists():
            parser.error(f'ZIP existente nao sera sobrescrito: {folder}.zip')
    output.mkdir(parents=True, exist_ok=True)
    for folder in FOLDERS:
        package(folder, output)


if __name__ == '__main__':
    main()
