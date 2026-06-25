opcao = -1
while opcao != 0:

    print("\n========== SAAS DOS BIGODES ==========")
    print("1- Cadastrar Cliente")
    print("2- Agendar Horário")
    print("3- Ver Agenda")
    print("4- Cancelar Agendamento")
    print("0- Sair do Sistema")

    opcao = int(input("Digite a opção desejada: "))

    if opcao == 1:
        print("Cadastrando cliente.")
    elif opcao == 2:
        print("Agendando horário.")
    elif opcao == 3:
        print("Vendo agenda.")
    elif opcao == 4:
        print("Cancelando agendamento.")
    elif opcao == 0:
        print("Obrigado por utilizar nosso sistema.")
        print("Saindo do sistema.")
    else:
        print("Digite uma opção valida.")