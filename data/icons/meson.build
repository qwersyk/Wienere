application_id = 'io.github.qwersyk.Wienere'

scalable_dir = 'hicolor' / 'scalable' / 'apps'
install_data(
  scalable_dir / ('@0@.svg').format(application_id),
  install_dir: get_option('datadir') / 'icons' / scalable_dir
)

symbolic_dir = 'hicolor' / 'symbolic' / 'apps'
install_data(
  symbolic_dir / ('@0@-symbolic.svg').format(application_id),
  install_dir: get_option('datadir') / 'icons' / symbolic_dir
)
symbolic_dir = join_paths(get_option('datadir'), 'icons/hicolor/symbolic/apps')

install_data (
    'paper-plane-symbolic.svg',
    install_dir: symbolic_dir
)
