"""tests 包（C10 A3）。

加本文件的目的：让 `python -m unittest tests.unit.<module>`（dotted-path）与
`python -m unittest discover -s tests/unit` 两种入口都能用**同一条包路径**导入
共享构造（`tests.unit._helpers`），不再依赖运行方注入 `sys.path`。
文件内容保持为空（离线守卫会扫描本目录下所有 .py）。
"""
