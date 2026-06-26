horarios = [ "07:00", "08:00", "09:00", "10:00", "11:00", "14:00", "15:00", "16:00", "17:00"]
agendamentos = []
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
        if len(clientes) == 0:
            print("Nenhum cliente cadastrado. Cadastre um primeiro.")
        else:
        
            
            print("Horários disponiveis.")
            for horario in horarios:
                ocupado = False
                for agendamento in agendamentos:
                    if horario == agendamento["horario"]:
                        ocupado = True
                if not ocupado:
                    print(horario)
            nome_cliente = input("Digite o nome do cliente: ")
            horario_escolhido = input("Digite o horário escolhido: ")
            horario_ocupado = False
            for agendamento in agendamentos:
                if horario_escolhido == agendamento["horario"]:
                    horario_ocupado = True
            if horario_ocupado:
                print("Horário ocupado. Selecione outro.")
            else:
                agendamento = {
                    "cliente": nome_cliente,
                    "horario": horario_escolhido
                } 
                agendamentos.append(agendamento)
                
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