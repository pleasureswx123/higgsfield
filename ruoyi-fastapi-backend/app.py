import uvicorn

from config.env import AppConfig
from server import create_app

if __name__ != '__main__':
    app = create_app()

if __name__ == '__main__':
    uvicorn.run(
        app='server:create_app',
        host=AppConfig.app_host,
        port=AppConfig.app_port,
        root_path=AppConfig.app_root_path,
        reload=AppConfig.app_reload,
        workers=AppConfig.app_workers,
        factory=True,
        # SSE 是长连接；退出/热重载不能无限等待，付费生成由独立工作器执行。
        timeout_graceful_shutdown=15,
    )
