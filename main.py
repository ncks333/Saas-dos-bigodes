clientes = []
opcao = -1
while opcao != 0:

    print("\n========== SAAS DOS BIGODES ==========")
    print("1- Cadastrar Cliente")
    print("2- Agendar Horário")
    print("3- Ver Agenda")
    print("4- Cancelar Agendamento")
    print("5- Ver Clientes")
    print("0- Sair do Sistema")

    opcao = int(input("Digite a opção desejada: "))

    if opcao == 1:
        nome = input("Digite o nome: ")
        telefone = input("Digite seu número telefone: ")
        cliente = {

            "nome": nome,
            "telefone": telefone

        }
        clientes.append(cliente)
        print("Cliente cadastrado com sucesso!")
    elif opcao == 2:
        print("Agendando horário.")
    elif opcao == 3:
        print("Vendo agenda.")
    elif opcao == 4:
        print("Cancelando agendamento.")
    elif opcao == 5:
        if len(clientes) == 0:
            print("Nenhum cliente cadastrado.")
        else:
            for cliente in  clientes:
                print(f"Nome: {cliente['nome']}")
                print(f"Telefone: {cliente['telefone']}")    
    elif opcao == 0:
        print("Obrigado por utilizar nosso sistema.")
        print("Saindo do sistema.")
    else:
        print("Digite uma opção valida.")