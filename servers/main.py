from argparse import ArgumentParser
from json import dumps
from typing import Final, Mapping

from aiohttp import web, WSMsgType
from anyio import Path

app = web.Application()

app['runtime'] = '0.0.0.0'
app['port'] = 8080
app['test_path'] = Path('workspace', 'results', 'tests', app['runtime'])
app['performance_path'] = Path('workspace', 'results', 'performance', app['runtime'])
app['fail_file'] = Path('workspace', '.fail')
app['meta_file'] = Path('workspace', '.meta')
app['maximum_post_payload'] = 52428800
app['maximum_websocket_payload'] = 1000000  # to disable the size limit use 0
app['maximum_binary_request_length'] = 16
app._client_max_size = app['maximum_post_payload']


async def ensure_directory_exists(directory_path) -> None:
    try:
        await Path.mkdir(directory_path, parents=True, exist_ok=True)
    except Exception as err:
        print(f'Error creating directory {directory_path}', err)
    else:
        print(f'Directory created successfully {directory_path}')


async def create_empty_file(file_path) -> None:
    dir_name = await Path(file_path).parent.absolute()

    # Ensure the directory exists before creating the file
    await ensure_directory_exists(dir_name)
    # Create an empty file
    await Path(file_path).touch()


async def create_meta_file(file_path, data) -> None:
    await create_empty_file(file_path)
    await Path(file_path).write_text(data)
# Endpoints
routes = web.RouteTableDef()


@routes.post('/tests')
async def store_test_to_disk(request) -> web.Response:
    body: Final[dict] = await request.json()

    target_name: Final[str] = 'html5' if body['isBrowser'] else body['targetName']
    runner_name: Final[str] = 'yyc' if body["isCompiled"] else 'vm'
    filesystem_type: Final[str] = '_sandboxed' if body['isSandboxed'] else ''

    file_name: Final[str] = f'{target_name}_{runner_name}{filesystem_type}'
    file_path: Final[Path] = Path(request.app['test_path']).with_name(file_name).with_suffix('.json')

    dir_name: Final[Path] = await Path(file_path).parent.absolute()
    await ensure_directory_exists(dir_name)
    try:
        await file_path.write_text(dumps(body))
    except Exception:
        print(f"Can't create test file in {file_path}!")
        await create_empty_file(request.app['fail_file'])

    # TODO: absolute path?
    data: Final[dict] = {'folder': str(request.app['test_path']), 'file': str(file_name)}
    await create_meta_file(request.app['meta_file'], dumps(data))

    return web.Response(text='Tests data stored')


@routes.post('/performance')
async def store_performance_to_disk(request) -> web.Response:
    body: Final[dict] = await request.json()
    file_name: Final[str] = f'{body["platformName"]}_{body["runnerName"]}'
    file_path: Final[Path] = Path(request.app['performance_path']).with_name(file_name).with_suffix('.json')

    dir_name: Final[Path] = await Path(file_path).parent.absolute()
    await ensure_directory_exists(dir_name)
    try:
        await file_path.write_text(dumps(body))
    except Exception:
        await create_empty_file(request.app['fail_file'])

    return web.Response(text="Performance data stored")


@routes.get('/websockets')
async def websocket_echo(request) -> web.WebSocketResponse:
    print('New websocket connection')
    ws = web.WebSocketResponse(max_msg_size=request.app['maximum_websocket_payload'])

    params: Mapping = request.rel_url.query
    request['mode'] = params['mode'] if 'mode' in params.keys() else 'raw'
    request['handshake'] = False

    await ws.prepare(request)

    async for msg in ws:
        match msg.type:
            case WSMsgType.ERROR:
                print(f'Websocket connection closed with exception: {ws.exception()}')
            case WSMsgType.CLOSE:
                print(f'Websocket server got close frame')
                break
            case WSMsgType.BINARY:
                if request['mode'] == 'handshake':
                    print('Starting Handshake')
                    request['handshake'] = True
                    await ws.send_bytes('GM:Studio-Connect\0'.encode())
                else:
                    print('Starting Echo')
                    # Just send the data back
                    await ws.send_bytes(msg.data)
                    print(msg.data)
            case _:
                print('Connection terminated!')
                break

    return ws


app.router.add_routes(routes)

server_launch_arguments = ArgumentParser()
server_launch_arguments.add_argument('runtime', default=app['runtime'], nargs='?', type=str)
server_launch_arguments.add_argument('port', default=app['port'], nargs='?', type=int)

if __name__ == '__main__':
    launch_args = server_launch_arguments.parse_args()
    app['runtime'] = launch_args.runtime
    app['port'] = launch_args.port
    web.run_app(app, port=app['port'])
