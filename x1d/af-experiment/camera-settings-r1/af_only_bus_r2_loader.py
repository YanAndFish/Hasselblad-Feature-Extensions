"""AF 独立装载入口，额外绑定 bus-startup-r2；原入口和历史报告保持原样。"""
import af_only_loader as runtime
runtime.VALIDATION = runtime.HERE / 'build/af-only-bus-r2-validation.json'

if __name__ == '__main__':
    runtime.main()
